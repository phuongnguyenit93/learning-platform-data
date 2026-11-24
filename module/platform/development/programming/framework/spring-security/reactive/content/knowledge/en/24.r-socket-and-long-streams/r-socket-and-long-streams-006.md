# Testing RSocket with Missing Authentication and Insufficient Permissions

## 1. Context: how does protecting RSocket differ from protecting HTTP?

**RSocket** is an asynchronous, bidirectional messaging protocol running over transports such as TCP or WebSocket. It supports four primary interaction models: **request-response**, **fire-and-forget**, **request-stream**, and **request-channel**. A connection can be long-lived, carrying many requests and many data streams. Therefore, security is not only about "whether there is a token before entering the controller," but also involves the **SETUP frame**, **per-request metadata**, permissions per **route**, and handling **already-started streams**.

In Spring Security Reactive, key components include:

- `@EnableRSocketSecurity` enables RSocket Security in the application context.
- `RSocketSecurity` provides the `authorizePayload(...)`, `simpleAuthentication(...)`, and `jwt(...)` DSLs.
- `PayloadSocketAcceptorInterceptor` integrates authentication/authorization interceptors into the RSocket socket acceptor.
- `AuthenticationPayloadInterceptor` coordinates with `ReactiveAuthenticationManager` to verify credentials.
- `AuthorizationPayloadInterceptor` checks the principal/authorities against `PayloadExchange` and route rules.
- `RSocketRequester` on the client sends metadata to authenticate on connect (`SETUP`) or per request.
- `StepVerifier` and a **real RSocket client/server in tests** verify success/error/cancel signals.

Our task is **testing missing authentication and insufficient permissions**. These two failures must be separated clearly:

1. **Unauthenticated**: the client sends no credentials/token for a protected route or sends invalid credentials. No trusted `Authentication` can be constructed.
2. **Authenticated, but unauthorized**: the user/token is valid and has an `Authentication`, yet lacks `ROLE_ADMIN`, authority, or scope required by the route.

> **Core difference from HTTP:** RSocket over TCP does not have HTTP **401/403** status codes per message. A security failure may reject the connection during `SETUP`, or a request's reactive Publisher may terminate with **`onError`** corresponding to an RSocket error frame. Do not write RSocket integration tests using `WebTestClient.expectStatus().isUnauthorized()`: that tests HTTP, not RSocket metadata/authentication.

### Learning outcomes

After this lesson, you can:

1. Distinguish **SETUP authentication** from **per-request authentication**, choosing the right test model.
2. Verify public routes need no credentials while protected routes reject anonymous requests.
3. Verify wrong credentials are rejected rather than treated as a low-privilege user.
4. Verify a `ROLE_READER` user can read valid routes but cannot call `ROLE_ADMIN` routes.
5. Verify a `ROLE_ADMIN` user can actually call the route, proving denied tests are not caused by broken routing.
6. Write **real TCP RSocket tests on a random port** using `@SpringBootTest`, `@LocalRSocketServerPort`, `RSocketRequester`, and `StepVerifier`.
7. Use `SimpleAuthenticationEncoder` / `UsernamePasswordMetadata` with the proper MIME type.
8. Test request-stream, item limits, and cancellation to avoid hanging tests.
9. Understand limitations of SETUP authentication on long-lived connections/streams: token expiration, logout, permission changes, and revocation **are not automatically rechecked on every event**.
10. Avoid leaking credentials, verify TLS requirements, and distinguish unit/mock tests from end-to-end tests.

## 2. Four RSocket interaction types and their impact on authorization

| Model | Initiating RSocket frame | Common reactive type | What to test |
| --- | --- | --- | --- |
| Request-response | `REQUEST_RESPONSE` | `Mono<T>` | Are anonymous/low-role callers blocked before the handler returns data? |
| Fire-and-forget | `REQUEST_FNF` | `Mono<Void>` | Are unauthorized requests blocked before side effects? Client may not see an application response |
| Request-stream | `REQUEST_STREAM` | `Flux<T>` | Blocked before the first item? After subscribe, are cancellation/backpressure right? |
| Request-channel | `REQUEST_CHANNEL` | `Flux<In>` → `Flux<Out>` | Under what policy are permissions checked for the initial request and subsequent messages/payloads? |

In HTTP, a request normally has a response status and body. In RSocket, a connection maintains many independent interactions, each with a stream ID or protocol state. **Rejecting one request does not necessarily close the entire connection**, whereas rejecting `SETUP` can prevent the connection from being established.

With `request-stream`, if authentication/authorization is only checked at stream start, a running stream **does not automatically query backend permissions for every item**. When security policy demands immediate revocation, a mechanism to recheck/close the stream/disconnect must be designed and tested separately.

## 3. Authentication and authorization in RSocket

### Authentication

Authentication turns **credentials** from RSocket metadata into a trusted `Authentication`:

```text
RSocket SETUP / REQUEST frame
    → metadata contains credentials/token
    → AuthenticationPayloadInterceptor
    → ReactiveAuthenticationManager
    → Authentication or onError
```

A connection can carry `UsernamePasswordMetadata` at `SETUP` (one-user-per-connection model) or per request (shared-connection multi-user model). Spring Security supports both. With JWT, Bearer metadata can be sent at SETUP or per request when `RSocketSecurity.jwt(...)` and `ReactiveJwtDecoder` are configured.

**Missing credentials** differs diagnostically from **wrong credentials**, though neither may result in an authenticated principal.

### Authorization

Authorization decides permissions on a **payload exchange**:

```java
rsocket.authorizePayload(authorize -> authorize
    .setup().permitAll()
    .route("public.ping").permitAll()
    .route("profile.current").authenticated()
    .route("admin.metrics").hasRole("ADMIN")
    .anyRequest().denyAll()
    .anyExchange().permitAll()
);
```

This is an **illustrative** configuration (implemented completely below). `hasRole("ADMIN")` corresponds to `ROLE_ADMIN` in Spring Security; `authenticated()` only requires a valid principal, without implying admin rights.

**Rule order matters**: Spring Security evaluates in order and picks the first matching rule. Putting `.anyRequest().authenticated()` before `.route("admin.metrics").hasRole("ADMIN")` can allow any logged-in user into the admin route without the role! That is a configuration vulnerability, not a test framework issue.

### `anyRequest()` vs. `anyExchange()`

Per Spring Security RSocket documentation:

- `anyRequest()` covers requests carrying routes/metadata for authorization checks.
- `anyExchange()` covers unmatched exchanges, which can include **continuation payloads without metadata** inside an interaction/stream.

A common pattern is **checking the initial request by route** followed by `.anyExchange().permitAll()` so routeless continuation data frames are not accidentally blocked. This **does not mean stream data is completely safe**: business logic must still check permissions per object/message when needed.

If an application has very strict security for request-channel, test the exact frame sequence and interaction types. Never infer that a `.route(...)` rule is automatically enforced on every individual element of a stream.

## 4. SETUP authentication vs. request-time authentication

| Characteristic | Authentication at `SETUP` | Per-request authentication |
| --- | --- | --- |
| When are credentials sent? | When creating the connection | When sending a message/route |
| Best fit | One user/client identity tied to one connection | Connection shared across multiple users/tasks |
| Route check | Based on principal established at setup | Based on request credentials or combined policy |
| Changing identity | Usually requires reconnecting or deliberate mechanism | Can send different credentials per request |
| Token expiry/revocation while stream runs | Risk of stale snapshot identity | Fresh token on new request; running streams still need their own policy |
| Mandatory tests | With/without setup metadata, wrong secret, roles, setup rejection | Missing/wrong metadata per route, no inheritance from another user |
| Risk when pooling connections | Attaching user A's identity then reusing for B | Must isolate and attach auth accurately per request |

### Testing SETUP: when the server allows guests to connect

If the rules are:

```java
.setup().permitAll()
.route("private.feed").authenticated()
```

A client **without setup metadata** can still open an RSocket connection, yet calling `private.feed` must receive **`onError`**. This is a useful design for testing two separate failures: **being able to connect** does not mean **a protected route can be called**.

### Testing immediate SETUP rejection

If the policy is:

```java
.setup().hasRole("CONNECT")
```

a client lacking `ROLE_CONNECT` may be rejected during socket establishment. In tests, **capture errors from `connectTcp`/`tcp` or the first signal** depending on API/runtime; do not force all setup errors to look like route-level exceptions. The main project below uses `.setup().permitAll()` so route-level denials can be tested without confusing them with connection errors.

### Do not confuse RSocket Simple Authentication with HTTP Basic

Spring Security RSocket currently supports the **Simple Authentication Metadata Extension**. `RSocketSecurity.basicAuthentication(...)` exists for compatibility but has been marked deprecated in Security 6.x releases; modern configuration prefers:

```java
.simpleAuthentication(Customizer.withDefaults())
```

The client uses **`SimpleAuthenticationEncoder`** together with **`UsernamePasswordMetadata`** attached under the proper MIME type. It is not an HTTP `Authorization: Basic` header. **Simple Authentication does not encrypt credentials**; in real environments you must use a secure transport (TLS/mTLS, WSS) and handle secrets safely.

## 5. Building a test matrix before writing code

Suppose the server declares:

- `public.ping` — public.
- `private.feed` — requires an authenticated user.
- `admin.metrics` — requires `ROLE_ADMIN`.
- `events.private` — a request-stream requiring an authenticated user.

We register two test users:

- `reader` with `ROLE_READER`.
- `admin` with `ROLE_READER` and `ROLE_ADMIN`.

| Test case | Setup metadata | Request metadata | Route | Expectation |
| --- | --- | --- | --- | --- |
| A | None | None | `public.ping` | Receives `"PONG"` |
| B | None | None | `private.feed` | `onError`, no private data |
| C | Valid `reader` | None | `private.feed` | Receives `"PRIVATE"` |
| D | Valid `reader` | None | `admin.metrics` | `onError`, metrics unseen |
| E | Valid `admin` | None | `admin.metrics` | Receives `"ADMIN_METRICS"` |
| F | `reader`/wrong password | None | `private.feed` | Connection or request error, no data returned |
| G | None | Valid `reader` | `private.feed` | Receives `"PRIVATE"` if per-request auth is enabled |
| H | None | None | `events.private` | `onError`, no events |
| I | Valid `reader` | None | `events.private` | Receives events; consumer can cancel early |
| J | None | Valid `admin` | `admin.metrics` | Receives `"ADMIN_METRICS"` if per-request auth is enabled |
| K | Valid `reader` | None | unlisted route | Denied, never silently permitted |
| L | Valid `admin` | None | public route | Still receives public data, no auth metadata leak |

**Do not test only a single negative case.** A route can return `onError` because **no controller exists**, codec mismatch, server not running, or transport failure. Therefore, every denied test needs a **positive control** for **that exact route** with an authorized user. Best practice also checks server-side invocation counters or audits to prove the controller never ran when denied.

## 6. Java 17+ example: RSocket TCP and Spring Security Reactive

The example below is a Spring Boot 3.x / Spring Security 6.x project using **standalone RSocket TCP on port 9898**. No HTTP REST endpoints are created and `WebTestClient` is not used; testing uses `RSocketRequester` connecting to a real RSocket server.

Configuration highlights:

- `SETUP` allows connections without credentials; each route has its own policy.
- `Simple Authentication` verifies username/password using `MapReactiveUserDetailsService`.
- Passwords are stored as **BCrypt-based encoded hashes** via an appropriate `PasswordEncoder` (no plaintext in the user repository).
- Four routes return mock data with no real secrets.
- Tests use a random TCP port (`spring.rsocket.server.port=0`) to avoid relying on port 9898 or CI conflicts.

**Limitation:** Localhost TCP tests omit TLS for convenience. **Do not deploy a configuration transmitting plaintext credentials over public TCP**; production requires TLS/mTLS or WebSocket Secure, auth contracts, and proper key/secret management.

### 6.1. Directory structure

```text
rsocket-security-tests/
  settings.gradle
  build.gradle
  src/main/resources/application.yml
  src/main/java/demo/rsocketauth/
    RSocketAuthApplication.java
    RSocketAuthSecurityConfig.java
    SecureMessageController.java
  src/test/java/demo/rsocketauth/
    RSocketSecurityIntegrationTest.java
```

### 6.2. `settings.gradle`

```groovy
rootProject.name = 'rsocket-security-tests'
```

### 6.3. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-rsocket'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    // RSocket security DSL, interceptors, metadata extensions.
    implementation 'org.springframework.security:spring-security-rsocket'
    implementation 'org.springframework.security:spring-security-messaging'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-rsocket` provides the RSocket server/client, Reactor Netty, and Spring Messaging; `spring-security-rsocket` provides `RSocketSecurity`/authentication interceptors, while `spring-boot-starter-security` provides authentication support. Use the Spring Boot BOM to select compatible versions; do not mix Spring Security 6.x with Framework/RSocket jars from other majors. `reactor-test` provides `StepVerifier`.

**`spring-boot-starter-web` is not needed** just to run standalone RSocket TCP. Spring Boot also supports RSocket over WebSocket on WebFlux with the right transport/mapping-path configuration; this lesson picks TCP to test fewer layers.

### 6.4. `src/main/resources/application.yml`

```yaml
spring:
  rsocket:
    server:
      port: 9898
      transport: tcp
```

`bootRun` opens the RSocket TCP server on port 9898. In tests, `@SpringBootTest(properties = "spring.rsocket.server.port=0")` overrides it to a **random free port** and `@LocalRSocketServerPort` retrieves the actual bound port.

**Do not confuse RSocket port with HTTP port**: `@LocalServerPort` is for HTTP servers; RSocket ports use `@LocalRSocketServerPort`.

### 6.5. `src/main/java/demo/rsocketauth/RSocketAuthApplication.java`

```java
package demo.rsocketauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RSocketAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(RSocketAuthApplication.class, args);
    }
}
```

### 6.6. `src/main/java/demo/rsocketauth/RSocketAuthSecurityConfig.java`

```java
package demo.rsocketauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.rsocket.EnableRSocketSecurity;
import org.springframework.security.config.annotation.rsocket.RSocketSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.rsocket.core.PayloadSocketAcceptorInterceptor;

@Configuration
@EnableRSocketSecurity
public class RSocketAuthSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        // Generates hashes with {bcrypt} prefix via DelegatingPasswordEncoder.
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService(
            PasswordEncoder encoder) {

        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("READER", "ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    PayloadSocketAcceptorInterceptor rsocketInterceptor(
            RSocketSecurity rsocket) {

        rsocket
            .authorizePayload(authorize -> authorize
                // Allow connecting so per-route denials can be tested.
                .setup().permitAll()

                .route("public.ping").permitAll()
                .route("private.feed").authenticated()
                .route("admin.metrics").hasRole("ADMIN")
                .route("events.private").authenticated()

                // Never accidentally open unspecified routes.
                .anyRequest().denyAll()

                // Continuation payloads without route metadata.
                .anyExchange().permitAll())
            .simpleAuthentication(Customizer.withDefaults());

        return rsocket.build();
    }
}
```

**Important QA points:**

1. `@EnableRSocketSecurity` and `RSocketSecurity` are **RSocket APIs**, not `@EnableWebFluxSecurity`/`ServerHttpSecurity` for HTTP.
2. With the right dependencies, Spring Boot automatically wires the RSocket Security socket acceptor interceptor into the RSocket server; do not attach the interceptor a second time if auto-configuration already does so.
3. `.setup().permitAll()` is **deliberate for the test**. Without credentials at `SETUP`, a connection can still be opened, yet protected routes are still denied.
4. `.route("admin.metrics").hasRole("ADMIN")` sits **before** the catch-all. An authenticated `reader` still lacks `ROLE_ADMIN`.
5. `.anyRequest().denyAll()` ensures new routes are not silently public; `.anyExchange().permitAll()` allows payloads without routing metadata belonging to an already-checked request. For multi-message channel apps, add content policies/checks at the domain layer.
6. `.simpleAuthentication(Customizer.withDefaults())` configures the decoder verifying RSocket Simple metadata. Not HTTP Basic; the client needs the metadata MIME type and encoder.
7. `MapReactiveUserDetailsService` is an **in-memory demo user store**. Demo passwords are visible right in the docs and must not be copied to production. Production uses a proper identity provider/secret management.
8. `PasswordEncoderFactories.createDelegatingPasswordEncoder()` generates hashes prefixed with algorithms like `{bcrypt}`, compatible with Spring Security's default password decoders. Raw passwords are not stored in the users bean.

### 6.7. `src/main/java/demo/rsocketauth/SecureMessageController.java`

```java
package demo.rsocketauth;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class SecureMessageController {

    private final AtomicInteger privateInvocations = new AtomicInteger();
    private final AtomicInteger adminInvocations = new AtomicInteger();

    @MessageMapping("public.ping")
    public Mono<String> ping() {
        return Mono.just("PONG");
    }

    @MessageMapping("private.feed")
    public Mono<String> privateFeed() {
        privateInvocations.incrementAndGet();
        return Mono.just("PRIVATE");
    }

    @MessageMapping("admin.metrics")
    public Mono<String> adminMetrics() {
        adminInvocations.incrementAndGet();
        return Mono.just("ADMIN_METRICS");
    }

    @MessageMapping("events.private")
    public Flux<String> privateEvents() {
        return Flux.interval(Duration.ofMillis(100))
            .map(index -> "event-" + index);
    }

    // Counter only for testing invocation, not a public API.
    public int privateCallCount() {
        return privateInvocations.get();
    }

    public int adminCallCount() {
        return adminInvocations.get();
    }
}
```

**Why have counters?** Negative tests can verify that **when blocked, the controller does not execute**. If you only assert `onError`, a nonexistent route or codec mismatch can also error out and trick you into thinking Security worked.

`Flux.interval` is a stream that **does not terminate naturally**, useful for testing cancellation. Production streams need backpressure, timeouts/quotas, data ownership, cleanup, and revocation policies. Tests must **cancel** after a few items instead of waiting forever on `verifyComplete()`.

Demo counters use `AtomicInteger` for basic thread safety in tests, not as an audit metric. Never use them to store login counts/failed password attempts in a real system.

## 7. RSocket client tests: standard metadata and encoders

### 7.1. Simple Authentication MIME type

Spring Security RSocket uses the well-known RSocket authentication MIME type:

```java
MimeType SIMPLE_AUTH_MIME =
    MimeTypeUtils.parseMimeType(
        WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());
```

Imports:

```java
import io.rsocket.metadata.WellKnownMimeType;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;
```

Use **`UsernamePasswordMetadata`**, never putting an HTTP Basic header into request metadata:

```java
UsernamePasswordMetadata credentials =
    new UsernamePasswordMetadata("reader", "reader-pass");
```

Imports:

```java
import org.springframework.security.rsocket.metadata.UsernamePasswordMetadata;
import org.springframework.security.rsocket.metadata.SimpleAuthenticationEncoder;
```

The requester needs `SimpleAuthenticationEncoder` to serialize `UsernamePasswordMetadata` into metadata bytes with the matching MIME. Spring Boot provides a prototype `RSocketRequester.Builder`; grab a **fresh builder** for each connection because the builder is stateful.

### 7.2. SETUP metadata

Direct connection example:

```java
RSocketRequester requester = builder
    .rsocketStrategies(strategies ->
        strategies.encoder(new SimpleAuthenticationEncoder()))
    .setupMetadata(
        new UsernamePasswordMetadata("reader", "reader-pass"),
        SIMPLE_AUTH_MIME)
    .tcp("localhost", 9898);
```

This illustrates building a client, not a standalone Java class. To test another user, create **a new builder** rather than reusing a builder that already had `.setupMetadata` from a previous user.

### 7.3. Per-request metadata

When a connection has no credentials, an individual request can supply them:

```java
Mono<String> response = requester
    .route("private.feed")
    .metadata(
        new UsernamePasswordMetadata("reader", "reader-pass"),
        SIMPLE_AUTH_MIME)
    .retrieveMono(String.class);
```

This is **per-request authentication** supported by Spring Security. Credentials do not appear in the business payload; metadata must be properly encoded and the transport protected by TLS in production.

**Do not blindly attach `UsernamePasswordMetadata` to every request of a requester shared across multiple users** if the value holds another user's credentials. Each request must carry the exact identity and scopes of the actor being served, never letting user B inherit user A.

## 8. Full integration test over real RSocket TCP

The file below can be placed at `src/test/java/demo/rsocketauth/RSocketSecurityIntegrationTest.java`. Tests use the real RSocket server auto-started by Spring Boot on a random port. No mocking of the Security interceptor or fake responses returning exceptions is needed.

### 8.1. Test code

```java
package demo.rsocketauth;

import java.time.Duration;

import io.rsocket.metadata.WellKnownMimeType;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.rsocket.server.LocalRSocketServerPort;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.security.rsocket.metadata.SimpleAuthenticationEncoder;
import org.springframework.security.rsocket.metadata.UsernamePasswordMetadata;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(properties = "spring.rsocket.server.port=0")
class RSocketSecurityIntegrationTest {

    private static final MimeType AUTH_MIME =
        MimeTypeUtils.parseMimeType(
            WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

    @LocalRSocketServerPort
    int port;

    @Autowired
    ObjectProvider<RSocketRequester.Builder> requesterBuilders;

    @Autowired
    SecureMessageController controller;

    // Builder is prototype and stateful: get a fresh builder each time.
    private RSocketRequester openAnonymousConnection() {
        return requesterBuilders.getObject()
            .rsocketStrategies(s ->
                s.encoder(new SimpleAuthenticationEncoder()))
            .tcp("localhost", port);
    }

    private RSocketRequester openConnection(
            String username, String password) {
        return requesterBuilders.getObject()
            .rsocketStrategies(s ->
                s.encoder(new SimpleAuthenticationEncoder()))
            .setupMetadata(
                new UsernamePasswordMetadata(username, password),
                AUTH_MIME)
            .tcp("localhost", port);
    }

    @Test
    void publicRouteWorksWithoutAuthentication() {
        RSocketRequester client = openAnonymousConnection();
        try {
            StepVerifier.create(
                    client.route("public.ping")
                        .retrieveMono(String.class))
                .expectNext("PONG")
                .verifyComplete();
        } finally {
            client.dispose();
        }
    }

    @Test
    void missingAuthenticationCannotReadPrivateRoute() {
        RSocketRequester client = openAnonymousConnection();
        try {
            int before = controller.privateCallCount();

            StepVerifier.create(
                    client.route("private.feed")
                        .retrieveMono(String.class))
                .expectError()
                .verify(Duration.ofSeconds(5));

            // Denied request must not invoke private controller.
            assertEquals(before, controller.privateCallCount());
        } finally {
            client.dispose();
        }
    }

    @Test
    void validReaderCanReadPrivateRoute() {
        RSocketRequester client =
            openConnection("reader", "reader-pass");
        try {
            StepVerifier.create(
                    client.route("private.feed")
                        .retrieveMono(String.class))
                .expectNext("PRIVATE")
                .verifyComplete();
        } finally {
            client.dispose();
        }
    }

    @Test
    void authenticatedReaderCannotReadAdminRoute() {
        RSocketRequester client =
            openConnection("reader", "reader-pass");
        try {
            int before = controller.adminCallCount();

            StepVerifier.create(
                    client.route("admin.metrics")
                        .retrieveMono(String.class))
                .expectError()
                .verify(Duration.ofSeconds(5));

            // Successful login does not imply having ROLE_ADMIN.
            assertEquals(before, controller.adminCallCount());
        } finally {
            client.dispose();
        }
    }

    @Test
    void validAdminCanReadSameAdminRoute() {
        RSocketRequester client =
            openConnection("admin", "admin-pass");
        try {
            StepVerifier.create(
                    client.route("admin.metrics")
                        .retrieveMono(String.class))
                .expectNext("ADMIN_METRICS")
                .verifyComplete();
        } finally {
            client.dispose();
        }
    }

    @Test
    void invalidPasswordNeverReadsPrivateData() {
        // Depending on timing/setup implementation, error may occur
        // during connect or on the subsequent request.
        StepVerifier.create(
                reactor.core.publisher.Mono.fromCallable(() ->
                        openConnection("reader", "wrong-password"))
                    .flatMap(client ->
                        client.route("private.feed")
                            .retrieveMono(String.class)
                            .doFinally(signal -> client.dispose())))
            .expectError()
            .verify(Duration.ofSeconds(5));
    }

    @Test
    void perRequestCredentialsCanAuthenticateGuestConnection() {
        RSocketRequester client = openAnonymousConnection();
        try {
            StepVerifier.create(
                    client.route("private.feed")
                        .metadata(
                            new UsernamePasswordMetadata(
                                "reader", "reader-pass"),
                            AUTH_MIME)
                        .retrieveMono(String.class))
                .expectNext("PRIVATE")
                .verifyComplete();
        } finally {
            client.dispose();
        }
    }

    @Test
    void missingAuthenticationCannotStartProtectedStream() {
        RSocketRequester client = openAnonymousConnection();
        try {
            StepVerifier.create(
                    client.route("events.private")
                        .retrieveFlux(String.class))
                .expectError()
                .verify(Duration.ofSeconds(5));
        } finally {
            client.dispose();
        }
    }

    @Test
    void authorizedStreamCanEmitAndBeCancelled() {
        RSocketRequester client =
            openConnection("reader", "reader-pass");
        try {
            StepVerifier.create(
                    client.route("events.private")
                        .retrieveFlux(String.class))
                .expectNext("event-0", "event-1")
                .thenCancel()
                .verify(Duration.ofSeconds(5));
        } finally {
            client.dispose();
        }
    }

    @Test
    void unknownRouteIsNotAccidentallyPublic() {
        RSocketRequester client =
            openConnection("reader", "reader-pass");
        try {
            StepVerifier.create(
                    client.route("admin.unknown")
                        .retrieveMono(String.class))
                .expectError()
                .verify(Duration.ofSeconds(5));
        } finally {
            client.dispose();
        }
    }
}
```

### 8.2. Reliability of the test suite

**These are real integration tests** of RSocket transport + Spring Messaging routes + RSocket Security interceptors + Simple Authentication, not mock MVC. They verify:

- Anonymous **can connect** due to `.setup().permitAll()` yet cannot read `private.feed`.
- The same route `private.feed` works for user `reader`, proving the denied test is not a "missing route" error.
- Authenticated `reader` still cannot access `admin.metrics`.
- `admin` accesses **that exact route** successfully.
- Wrong credentials never return private content.
- Per-request metadata can authenticate on an initially anonymous connection.
- Unauthenticated request-stream emits no events; a valid user receives data and can cancel.
- Controller counters do not increment when a request is denied, and do increment when the positive case enters the handler.

**Do not assert verbatim exception messages** like `"Access Denied"` or `"Unauthorized"`; how Spring Security/RSocket Java maps exceptions into RSocket frames/messages can vary across versions. The test suite deliberately checks `onError` alongside positive controls and invocation counters, avoiding false-green tests tied to hardcoded text.

**Note when running tests in parallel:** `AtomicInteger` counters in the singleton controller are shared across methods; JUnit runs sequentially by default in many projects, but enabling `junit.jupiter.execution.parallel.enabled=true` can cause concurrent tests to affect `before/after` counter assertions. When running in parallel, isolate contexts/counters per request ID, use spies with interaction isolation, or avoid global counters.

### 8.3. Running tests

```bash
# Linux/macOS:
./gradlew test --tests 'demo.rsocketauth.RSocketSecurityIntegrationTest'

# Windows:
gradlew.bat test --tests "demo.rsocketauth.RSocketSecurityIntegrationTest"

# All tests in project:
./gradlew test
```

Example **expected results** by test logic:

```text
publicRouteWorksWithoutAuthentication          PASS
missingAuthenticationCannotReadPrivateRoute    PASS
validReaderCanReadPrivateRoute                 PASS
authenticatedReaderCannotReadAdminRoute        PASS
validAdminCanReadSameAdminRoute                PASS
invalidPasswordNeverReadsPrivateData           PASS
perRequestCredentialsCanAuthenticateGuestConnection PASS
missingAuthenticationCannotStartProtectedStream PASS
authorizedStreamCanEmitAndBeCancelled          PASS
unknownRouteIsNotAccidentallyPublic            PASS
```

The list above describes **expected test results**, not an actual Gradle log run here. In other environments, verify Boot/RSocket configuration and real test outcomes. If tests fail due to codec/connection/port errors instead of authorization, fix that root cause—**do not count it as a valid Security denial**.

## 9. Why must "insufficient permission" tests prove the user is authenticated?

A common mistake:

```java
StepVerifier.create(
    anonymousRequester.route("admin.metrics")
        .retrieveMono(String.class))
    .expectError()
    .verify();
```

This test **does not prove the route is checking `ROLE_ADMIN`**. It only proves an anonymous request fails; even a config with just `.authenticated()` would make it fail.

To prove **authorization**:

1. Prepare a valid user `reader` with `ROLE_READER`, without `ROLE_ADMIN`.
2. Call `private.feed` as that exact user and **receive a successful response**.
3. Call `admin.metrics` also as that user and receive **`onError`**.
4. Call **the same admin route** as `admin` with `ROLE_ADMIN`, receiving success.
5. Verify the protected handler did not run on the denied path.
6. To be sure the rule cannot be bypassed, verify `.route("admin.metrics").hasRole("ADMIN")` comes before `.anyRequest().authenticated()`.

This three-tier test separates **"user is unauthenticated"** from **"user is authenticated but lacks authority"**. Never treat a client `"Denied"` message as the sole proof.

### When the app uses scopes instead of roles

With JWT, authorities may carry the `SCOPE_` prefix, e.g., `SCOPE_reports.read`. In an RSocket Security rule you can use:

```java
.route("reports.read").hasAuthority("SCOPE_reports.read")
```

Do not write `.hasRole("reports.read")` if token mapping produces `SCOPE_reports.read`. `hasRole("ADMIN")` normally checks `ROLE_ADMIN`, not automatically derived from JWT `scope`.

If domain-level ownership/tenant checks exist, a token with `SCOPE_reports.read` **does not automatically grant access to every report**; you need a custom reactive authorization manager or checks in service logic by principal and resource ID.

## 10. Testing at the SETUP level: another policy model

The project above intentionally allows anonymous setup. For a **service-to-service RSocket connection** requiring client identity immediately on connect, an alternative policy can be:

```java
// Alternative option, do not combine with the main config:
rsocket.authorizePayload(authorize -> authorize
    .setup().hasRole("CONNECT")
    .route("public.ping").permitAll()
    .route("admin.metrics").hasRole("ADMIN")
    .anyRequest().authenticated()
    .anyExchange().permitAll()
);
```

A user with `ROLE_CONNECT` can establish a connection, yet **does not automatically gain `ROLE_ADMIN`**. Tests needed:

- Missing setup credentials → setup/connection rejected.
- Wrong setup credentials → rejected.
- Valid credentials missing `ROLE_CONNECT` → rejected right at SETUP.
- User with `ROLE_CONNECT` (no `ROLE_ADMIN`) → connects successfully, admin route denied.
- User with both `ROLE_CONNECT` and `ROLE_ADMIN` → connects and calls admin route successfully.

This is a **separate test variant**, not an extension enabled in the main example. If you simply change `.setup().hasRole("CONNECT")` without granting `ROLE_CONNECT` to any user, all connections will be rejected and route-level tests cannot run. That is a misconfigured test, not proof of proper route authorization.

### Catching SETUP errors when connecting asynchronously

The `RSocketRequester` API has variants returning `Mono<RSocketRequester>` for connection or synchronous requester creation methods depending on Framework version. When connecting may fail before any request, one test wrapper pattern is:

```java
Mono<String> attempt = Mono.fromCallable(() ->
        requesterBuilderWithSetupMetadata.tcp("localhost", port))
    .flatMap(requester ->
        requester.route("private.feed")
            .retrieveMono(String.class)
            .doFinally(signal -> requester.dispose()));
```

`requesterBuilderWithSetupMetadata` here is an **illustrative variable**, already configured with an `RSocketRequester.Builder` holding setup credentials. The goal is to prevent a connect-time exception from firing **before** `StepVerifier` subscribes to the publisher. Never call `Mono.fromCallable(() -> connect()).block()` on the Netty event loop; in a JUnit test, creating the client on the test thread is a different situation.

**Protocol note:** RSocket SETUP rejection is not an HTTP `401`; there is usually an RSocket error code such as `REJECTED_SETUP` at the connection layer. Exact exception/error text is a transport/runtime detail; assert by event semantics and error types appropriate to the library version used.

## 11. Long-lived request-stream: tests must not stop at the first element

RSocket is frequently used for telemetry, real-time prices/orders, subscription feeds, and IoT devices. These streams live much longer than a single HTTP request-response.

A protected stream should have at least these tests:

1. **Anonymous subscription** to a protected route → receives no events, publisher emits `onError`.
2. **Authenticated, authorized** → receives several events in order, can cancel.
3. **Authenticated, lacking permission** on an admin stream → receives zero events.
4. **Cancellation** from client → upstream is released per policy, without infinite background processing.
5. **Backpressure** when subscriber demands fewer items than emission rate → does not consume unbounded memory; test `request(n)`, buffering/drop policies if domain requires.
6. **Connection drop/reconnect** → never accidentally reuses another principal's context.
7. **Token expiration mid-stream** (with JWT/SETUP auth) → revocation/reauth behavior must be designed and tested; never assume the framework auto-closes streams.
8. **Role or tenant membership revoked after subscribe** → decide whether to cut the stream immediately or check on next subscription; implement proactively if required.

The test in section 8 uses:

```java
StepVerifier.create(
    client.route("events.private").retrieveFlux(String.class))
    .expectNext("event-0", "event-1")
    .thenCancel()
    .verify(Duration.ofSeconds(5));
```

It proves the stream starts when authenticated and the client can cancel after two items. It **does not** prove the backend handles mid-stream revocation, nor does it measure backpressure/cancellation cleanup. Those require extra instrumentation, test clocks/virtual time, or integration tests with fake IdP/revocation events.

### Caution with `StepVerifier.withVirtualTime`

`withVirtualTime` can test an internal `Flux.interval` with `VirtualTimeScheduler` if the publisher is created lazily and all timers are controllable. However, over **real RSocket transport/networking**, Netty socket clocks, TLS, scheduling, and remote servers do not automatically switch to virtual time. Thus this lesson uses `Duration.ofMillis(100)` and a 5-second total timeout over real TCP; never put `withVirtualTime` and assume time fast-forwards on the server too.

## 12. When using JWT/Bearer instead of Simple Authentication

RSocket Security supports the **Bearer Authentication Metadata Extension**, commonly used when an application accepts JWT access tokens instead of username/password.

Server:

```java
@Bean
PayloadSocketAcceptorInterceptor rsocketInterceptor(
        RSocketSecurity rsocket) {
    rsocket
        .authorizePayload(authorize -> authorize
            .setup().permitAll()
            .route("public.ping").permitAll()
            .route("reports.read")
                .hasAuthority("SCOPE_reports.read")
            .anyRequest().authenticated()
            .anyExchange().permitAll())
        .jwt(Customizer.withDefaults());
    return rsocket.build();
}
```

This is an **alternative configuration**; do not enable it simultaneously with `.simpleAuthentication` in the main example without explicitly designing multi-mechanism resolution. To configure `.jwt(...)`, Spring Security needs an appropriate `ReactiveJwtDecoder` bean; issuer/JWK trust, signature, `exp`, `nbf`, and `aud`/scope mapping must be verified per policy.

The client sends a `BearerTokenMetadata` at SETUP or per request:

```java
MimeType authMime = MimeTypeUtils.parseMimeType(
    WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

BearerTokenMetadata bearer =
    new BearerTokenMetadata(accessToken);

// SETUP:
RSocketRequester requester = builder
    .setupMetadata(bearer, authMime)
    .tcp("localhost", port);

// Or per request:
Mono<String> result = requester.route("reports.read")
    .metadata(bearer, authMime)
    .retrieveMono(String.class);
```

**This is an integration snippet, not a standalone class**: `accessToken`, `port`, and `builder` must be configured in a real program. Import `org.springframework.security.rsocket.metadata.BearerTokenMetadata`. The JWT must be issued by a trusted issuer; never use a self-crafted string or an ID token in place of a Resource Server access token.

### Matrix for RSocket JWT

| JWT/token | Context | Expectation |
| --- | --- | --- |
| Missing Bearer metadata | Protected route | `onError` |
| Malformed Bearer | Cannot decode | `onError` authentication |
| JWT wrong signature | Signature invalid | `onError` authentication |
| Expired JWT | `exp` exceeded | `onError` authentication |
| Valid JWT, missing `SCOPE_reports.read` | Authenticated but lacks permission | `onError` authorization |
| Valid JWT, has `SCOPE_reports.read` | Sufficient scope | Data success |
| Valid issuer JWT, wrong audience | Rejected by API policy | `onError` authentication |
| Valid JWT at SETUP, expires after 1 hour | Connection/stream stays open | Depends on reauth/revocation design, **not automatically cut** |

**Truly testing JWT validation:** issue JWTs signed with a **test private key**, provide a trusted test JWKS/public key, and configure a test `ReactiveJwtDecoder`. Never use mocked authentication and claim you tested signature, expiry, or issuer. If you only want to test route scope policy, an already-authenticated mock is helpful, but explicitly note that it skips the cryptographic verification layer.

## 13. Errors and statuses: RSocket does not use HTTP 401/403 per route

A few differences that often cause wrong tests:

| Error | Typical HTTP REST | RSocket over TCP |
| --- | --- | --- |
| Missing credentials | 401 | Setup rejection or request publisher `onError` |
| Wrong credentials | 401 | Authentication failure, RSocket error |
| Valid user missing role/scope | 403 | Authorization denial, RSocket error |
| Nonexistent route | 404 | Routing/handler RSocket error |
| Wrong codec, malformed payload | 400 | Decode/serialization error over RSocket |
| Socket disconnected | Network error | Error/connection termination; does not prove Security denial |
| Setup rejected | No direct HTTP equivalent | RSocket `REJECTED_SETUP` or matching protocol error type |
| Request response error | Has HTTP status | RSocket `ERROR` frame / `onError` |

**Do not rely on a single `"Access Denied"` string** to classify errors. Check that the route exists, the test user's credentials verify on another route, the role is right, and when needed inspect `RSocketErrorException.errorCode` or server audits/metrics per version.

Libraries/clients may wrap errors into different exception wrappers. In production apps, define a **safe error contract** for clients without returning raw credentials, JWTs, security contexts, or backend stack traces in RSocket error messages. If domain-level error codes are needed, distinguish authentication failure, authorization denied, and payload validation error.

## 14. Do not forget `request-channel` and fire-and-forget

### Fire-and-forget

With `REQUEST_FNF`, the client **receives no business response payload** confirming whether the server accepted or rejected the operation. A publisher completion on the client may merely mean the frame was sent, not that the server side effect occurred. When testing authorization for fire-and-forget with side effects:

1. Send requests from guest/reader/admin per the matrix.
2. Verify server-side audited invocation/side effect **did not happen** when unauthorized.
3. Wait for state confirmation via a dedicated test mechanism (repository/fake service/metrics), rather than asserting only `Mono<Void>` completion.
4. Avoid timeouts/races that produce false-green tests.
5. For business requirements needing guaranteed outcomes, consider request-response/ack protocols instead of pure FNF.

### Request-channel

`REQUEST_CHANNEL` is a bidirectional data stream; payload frames may not carry route metadata after the first frame. If route checks run only on the initial request, an authorized client could send new items throughout the call. You must:

- Define per-channel or per-item authorization.
- Check each item's tenant/resource ID at the service layer.
- Bound data sizes and enforce backpressure.
- Test cancellation and client reconnect.
- If principal/token changes between items, design explicit reauthentication or channel closure policies.
- Test missing permission on the **initial frame** and behavior when permission is revoked **mid-channel** if business requirements demand it.

Never use `.anyExchange().permitAll()` as an excuse to skip all service checks when messages carry sensitive data.

## 15. Testing scenarios for revocation, logout, and long connections

When authenticating at SETUP, authorization may rely on the principal created when establishing the connection. Removing a user's role in the DB afterward **does not automatically change the `Authentication` object already living on the socket**.

Example:

```text
T0: user reader connects, carrying ROLE_READER.
T1: server allows events.private subscription.
T2: IAM system disables reader.
T3: stream keeps emitting data without custom reauth/revocation logic.
```

If the product requires **cutting the stream at T2**, implement one of these measures:

- Close sockets/streams upon receiving a revocation event from the identity provider or policy service.
- Use short-lived tokens and require periodic reauthentication or reconnection.
- For each sensitive event, check permissions/tenant at the data source or stream pipeline, with intentionally short cache TTLs.
- Cap connection/stream lifetime per policy.
- Ensure idempotent cleanup and prevent races that emit further data after revocation beyond documented tolerance.

**Do not just set `JWT exp=60s` and assume the stream cuts off after 60 seconds.** JWT validation usually runs when authentication occurs; an already-authorized stream may continue unless a recheck policy is added.

Revocation tests must control timing (appropriate latches/test sinks/virtual clocks), emit some events before revocation, then revoke and verify no more sensitive events arrive or a termination signal arrives within the defined SLA.

## 16. Transport and metadata security issues

RSocket Simple Authentication sends **username/password as structured metadata**, without encrypting those values. Metadata is not a separate secure channel; if a TCP connection lacks TLS, eavesdroppers can observe credentials or payloads.

Therefore:

1. Use non-TLS localhost TCP tests solely for practicing APIs/tests.
2. Production uses TLS/mTLS for TCP, or WebSocket Secure (`wss://`) when deployed over WebSocket.
3. Enforce server identity, certificate trust, and key rotation per organizational policy.
4. Never log raw RSocket frames, setup metadata, Simple credentials, Bearer tokens, or payload PII when debug logging is enabled.
5. Never put passwords/tokens into `.route("...")` or `setupData` as easily logged strings.
6. Cap metadata/payload sizes, connection counts, stream counts, backpressure request counts, and connection rates.
7. Rate-limit failed authentication attempts and audit error categories using safe correlation IDs.
8. With pooled/shared connections, never attach user credentials at SETUP and accidentally reuse them for other users' requests.
9. Verify `@MessageMapping` is actually protected by the Security interceptor; custom server bootstraps may need to attach `SecuritySocketAcceptorInterceptor` manually.
10. Test network reconnect, session resumption, and revocation in real deployments—do not extrapolate from one localhost test.

## 17. Testing method-level/domain authorization

`RSocketSecurity.authorizePayload(...)` rules act as a **pre-handler guard** based on route/principal. For business logic involving many reports, orders, or tenants, you must check **permissions on the specific object**:

```text
admin.metrics        → ROLE_ADMIN
report.read.{id}     → SCOPE_reports.read AND principal is permitted to read id
project.events.{id}  → principal must belong to this project/tenant
```

`ROLE_ADMIN`/`SCOPE_reports.read` alone does not solve **object-level authorization**. You can use a custom `ReactiveAuthorizationManager<PayloadExchange>` or check in the service using the verified principal and trusted resource ID. Separate:

- Route-level guard blocking users lacking baseline permissions.
- Domain guard checking ownership, tenant, project membership, and resource state.
- Stream policy deciding whether permissions must be re-evaluated while emitting events.

Negative tests must include:

- Alice can read project A, cannot read project B.
- Bob with the same role in a different tenant cannot read Alice's data.
- Changing route parameters/resource IDs does not leak data.
- Missing/invalid metadata returns no sensitive documents.
- Error messages do not reveal whether a resource exists if domain policy requires it.

If using Reactive Method Security annotations, verify `@EnableReactiveMethodSecurity` is enabled, proxy boundaries, and Reactor Context inside RSocket handlers. Never assume HTTP method-security annotations automatically apply to every RSocket route without enabling and testing them.

## 18. Diagnosing failing RSocket tests

| Symptom | Common cause | What to check |
| --- | --- | --- |
| Every request reports connection refused | RSocket server not bound, wrong port | `spring.rsocket.server.port`, `@LocalRSocketServerPort` |
| Anonymous test returns data from private route | Security interceptor not attached, overly broad public rule | `@EnableRSocketSecurity`, dependencies, Boot RSocket auto-config |
| Reader can call admin | Catch-all `.authenticated()` placed before `.hasRole("ADMIN")` | `authorizePayload` order |
| Reader cannot call private route | Simple metadata wrong MIME/encoder, wrong password, missing auth config | `SimpleAuthenticationEncoder`, `UsernamePasswordMetadata` |
| Reader cannot connect | `.setup().hasRole(...)` too strict or setup metadata lost | SETUP policy and user roles |
| Anonymous cannot connect despite `.setup().permitAll()` | Malformed auth metadata sent/codec error or another setup handler | Requester builder and SETUP metadata |
| `.expectError()` passes because route doesn't exist | No positive control | Test the same route with valid admin/reader |
| Passes on machine A, fails in CI | Fixed port, race, scheduler/cold start | Random port and bounded timeouts |
| Request-stream test hangs forever | Infinite Flux, test waits for `verifyComplete()` | Use `.thenCancel().verify(Duration)` |
| Fire-and-forget `Mono<Void>` completes yet side effect occurs | Test confused send-completion with authorization | Inspect server-side side effects/audits |
| Token expired yet stream keeps emitting | No mid-stream reauth | Revocation/stream lifecycle policy |
| Guest calling public route errors | `.anyRequest().authenticated()` placed before public rule | Policy order |
| Authenticated requests after logout still succeed | Connection-level principal persists | Close connection/re-auth rules |
| Error is a serialization/codec exception | Data MIME or DTO mismatch | Test codec/serialization; do not conflate with auth deny |
| Client A requests use identity B | Shared builder/requester with setup metadata B | Separate connections or explicit per-request auth |
| Logs contain passwords/tokens | Raw RSocket frame logging | Redact/auth audits |
| Unit security tests pass yet prod route is open | Mock did not wire real socket interceptor | TCP integration tests + deployment validation |

### Eight-step debugging workflow

1. **Classify transport first**: is the connection established? Are TCP or WebSocket port/transport right?
2. **Check the security interceptor**: did Spring Boot actually wire `PayloadSocketAcceptorInterceptor`/`SecuritySocketAcceptorInterceptor`?
3. **Check metadata**: are `MESSAGE_RSOCKET_AUTHENTICATION`, encoder, and `UsernamePasswordMetadata`/Bearer token in the right place (SETUP vs. REQUEST)?
4. **Check rules and order**: do `.setup`, `.route`, `.anyRequest`, `.anyExchange` have a loose rule before a strict rule?
5. **Distinguish authentication/authorization**: can `reader` call a normal route before concluding `admin` lacks permissions?
6. **Check positive/negative controls**: the same admin route succeeds with the right role; handler invocation does not happen on the denied path.
7. **For streams**, verify item counts before/after revocation, cancellation, connection lifetime, and backpressure.
8. **Check secret hygiene**: no logged credentials, sensitive stack traces, or raw frames; TLS enabled in real environments.

## 19. Common mistakes to avoid

**Mistake 1 — Using `WebTestClient` to assert 401/403 for RSocket TCP.**  
RSocket does not use HTTP response statuses per route. Use `RSocketRequester` and `StepVerifier` or low-level RSocket Java test tools.

**Mistake 2 — Testing insufficient permissions using only an anonymous user.**  
Anonymous rejection does not prove a route requires `ROLE_ADMIN`; you must have an authenticated reader and a positive admin control.

**Mistake 3 — Calling `builder.tcp(...)` before adding `SimpleAuthenticationEncoder`.**  
`UsernamePasswordMetadata` requires the right encoder; register it in Spring `RSocketStrategies` before connecting/sending.

**Mistake 4 — Forgetting the authentication metadata MIME type.**  
Use `MESSAGE_RSOCKET_AUTHENTICATION` when sending Simple/Bearer metadata, never an arbitrary string.

**Mistake 5 — Sending credentials at SETUP and expecting another user's later requests to switch identity automatically.**  
Setup identity is typically bound to the connection. Shared connections need intentionally designed per-request authentication.

**Mistake 6 — Placing `.anyRequest().authenticated()` before `.route("admin.metrics").hasRole("ADMIN")`.**  
First-match-wins lets any logged-in user into the admin route.

**Mistake 7 — Using `.anyExchange().permitAll()` as an excuse to skip object-level authorization.**  
Route guard and domain guard are two distinct layers; request-channel/stream needs its own policy.

**Mistake 8 — Treating RSocket FNF `Mono.empty()` as proof the server executed a side effect.**  
There is no application response payload to confirm execution; verify server-side state/audits.

**Mistake 9 — Calling `verifyComplete()` on an infinite stream.**  
The test hangs; use `expectNextCount(n)`, `thenCancel`, and `verify(Duration...)`.

**Mistake 10 — Skipping TLS because Simple Authentication "has an encoder."**  
The encoder serializes metadata; it **does not encrypt transport**. Credentials can be exposed.

**Mistake 11 — Assuming a JWT expiring at minute 10 auto-disconnects a stream opened at minute 0.**  
There is no guaranteed mid-stream reauth unless explicitly designed and tested.

**Mistake 12 — Using a single exception message string to identify all security failures.**  
Transport, routing, codec, and authorization can all produce `onError`; use categorization and positive controls.

**Mistake 13 — Testing with a fixed port in CI.**  
Port 9898 may be busy; use `spring.rsocket.server.port=0` and `@LocalRSocketServerPort`.

**Mistake 14 — Failing to `dispose()` requesters after tests.**  
RSocket connections/threads may stay alive between tests, causing flakiness and resource leaks.

**Mistake 15 — Logging raw RSocket setup frames.**  
Simple metadata/Bearer tokens can leak into logs/traces; redact them.

## 20. Production/test checklist

| Item | Criteria |
| --- | --- |
| RSocket Security | `@EnableRSocketSecurity`, real interceptor wired |
| SETUP policy | Guest connection vs. required setup role clearly defined |
| Route policy | Public, authenticated, and `ROLE_ADMIN` separated |
| Rule order | Strict rules placed before catch-all |
| Metadata | Proper `MESSAGE_RSOCKET_AUTHENTICATION` MIME |
| Client codec | `SimpleAuthenticationEncoder` present when using Simple auth |
| Requester isolation | Never share a wrong actor's setup user identity |
| Missing credentials | Protected route returns `onError`, leaks no data |
| Wrong credentials | Does not establish trusted authentication |
| Insufficient authority | Valid reader cannot call admin route |
| Positive controls | Reader private succeeds; admin admin succeeds |
| No handler execution | Denied path never invokes private handler |
| Random test port | `@LocalRSocketServerPort` instead of hardcoded port |
| Bounded tests | `StepVerifier.verify(Duration...)`, stream cancel |
| FNF/channel | Check server side effects and per-item policy |
| Long-lived streams | Contract for revocation/role change/expiry behavior |
| JWT if used | Trusted JWK/issuer/audience/expiry/scope |
| TLS | Simple credentials/tokens travel only over secure channels |
| Observability | Classify transport/authN/authZ, never log credentials |
| Cleanup | `requester.dispose()` after each test |
| CI | No fixed thread/order/port dependencies, isolated tests |

## 21. Self-check questions

**1. Why shouldn't anonymous RSocket tests use `WebTestClient.expectStatus().isUnauthorized()`?**  
Because RSocket routes over TCP have no per-frame HTTP 401 response; check RSocket error signals/connection failures using `RSocketRequester` and `StepVerifier`.

**2. If a client can connect without auth, does that mean every route is public?**  
No. `.setup().permitAll()` only permits SETUP; routes can still require `authenticated()` or roles.

**3. How do you prove an "insufficient permission" failure rather than "missing authentication"?**  
Use valid `reader` credentials, verify they call a private route successfully, then assert the admin route is denied; `admin` with the role calls that same route successfully.

**4. Which authority does `hasRole("ADMIN")` require?**  
`ROLE_ADMIN` per Spring Security's default prefix.

**5. Why is `SimpleAuthenticationEncoder` needed?**  
To serialize `UsernamePasswordMetadata` into RSocket Simple Authentication metadata with the right MIME; the encoder is not security encryption.

**6. Are setup credentials always refreshed inside an already-open request-stream?**  
Not by default. An authentication/authorization snapshot may live with the connection/stream; a dedicated reauth/revocation policy is needed if required.

**7. Are `anyRequest()` and `anyExchange()` the same?**  
No. One covers requests with metadata/routes, while the other covers unmatched exchanges, including subsequent routeless payloads in some models.

**8. Why does `expectError()` need a positive control?**  
Because codec errors, nonexistent routes, or transport errors can also end with `onError` unrelated to security.

**9. When testing an infinite request-stream, how do you stop the test?**  
Receive a few elements, then call `.thenCancel()` and `.verify(Duration...)`.

**10. Does an anonymous FNF request completing on the client prove the handler was invoked?**  
No. FNF has no response payload to confirm processing; inspect server-side side effects/audits.

**11. When using JWT with RSocket, can you just read `scope` from an unverified payload?**  
No. The resource side must verify signature, issuer, audience, expiry, and authority mapping before authorizing.

**12. Why is TLS needed with Simple Authentication?**  
Because username/password are serialized in metadata rather than encrypted by the encoding; the transport must provide confidentiality and authenticity.

## Key takeaways

- **RSocket Security checks `SETUP` and route/request payloads**, without returning HTTP 401/403 per message over TCP.
- **Missing authentication** differs from **authenticated but lacking permission**; test anonymous, invalid credentials, `reader`, and `admin`.
- Use `RSocketRequester` + `StepVerifier`, verifying `onError` and positive controls on the same route, rather than relying solely on message text.
- `RSocketSecurity.authorizePayload(...)` evaluates rules in order; `hasRole("ADMIN")` requires `ROLE_ADMIN`.
- `SimpleAuthenticationEncoder` + `UsernamePasswordMetadata` + `MESSAGE_RSOCKET_AUTHENTICATION` form the essential trio for sending Simple metadata.
- **Request-streams need bounded tests** with cancellation, and **long-lived sessions** need dedicated revocation/reauth designs.
- **Never expose credentials over transport/logs**; Simple Auth metadata does not replace TLS.
- With JWT, test cryptographic validation separately; `SCOPE_` authorities are not automatically equivalent to `ROLE_`.

### Official references

- [Spring Security 6.5 — RSocket Security](https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/rsocket.html)
- [Spring Security 6.5 — RSocketSecurity API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/rsocket/RSocketSecurity.html)
- [Spring Security 6.5 — PayloadSocketAcceptorInterceptor API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/rsocket/core/PayloadSocketAcceptorInterceptor.html)
- [Spring Security 6.5 — SimpleAuthenticationEncoder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/rsocket/metadata/SimpleAuthenticationEncoder.html)
- [Spring Boot 3.5 — RSocket](https://docs.spring.io/spring-boot/3.5/reference/messaging/rsocket.html)
- [Spring Framework 6.2 — RSocket](https://docs.spring.io/spring-framework/reference/6.2/rsocket.html)
- [Spring Boot — LocalRSocketServerPort API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/rsocket/server/LocalRSocketServerPort.html)
- [Project Reactor — Testing Reactive Sequences](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Spring Blog — Getting Started with RSocket: Spring Security](https://spring.io/blog/2020/06/17/getting-started-with-rsocket-spring-security/)
