# Configuring @EnableRSocketSecurity, RSocketSecurity, and SocketAcceptorInterceptor

*Module: Spring Security - reactive · Group: RSocket and long streams · Java 17+ / Spring Security 6.5 / Spring Boot 3.5.x.*

## 1. Security goals and context

RSocket provides bidirectional communication over TCP or WebSocket with the request-response, fire-and-forget, request-stream, and request-channel models. A connection can be long-lived and carry many requests or many payloads; unlike HTTP, when an identity is authenticated at **SETUP** time, subsequent requests on the connection can use this context.

Spring Security for WebFlux HTTP uses `ServerHttpSecurity`, `SecurityWebFilterChain`, and `WebFilter`. **RSocket is not automatically protected by those HTTP rules**. To protect RSocket routes, Spring Security provides:

- **`@EnableRSocketSecurity`**: enables RSocket Security configuration support.
- **`RSocketSecurity`**: DSL for declaring authentication and authorization rules for SETUP/route/request exchanges.
- **`PayloadSocketAcceptorInterceptor`**: result of `RSocketSecurity.build()`, applying the chain of payload interceptors.
- **`SecuritySocketAcceptorInterceptor`**: bridge that plugs payload security into the RSocket server via `SocketAcceptorInterceptor`.
- **`RSocketSecurityAutoConfiguration`**: Spring Boot automatically wires the bridge into the RSocket server when the right dependencies/beans are present.
- **`AuthenticationPayloadInterceptor`**: coordinates the converter and `ReactiveAuthenticationManager` to authenticate credentials.
- **`AuthorizationPayloadInterceptor`**: uses `ReactiveAuthorizationManager`/DSL to evaluate route and setup permissions.
- **`RSocketRequester`**: client API for creating connections and sending routes, data, and authentication metadata.

**Learning outcomes:** you will know how to set up the right beans and dependencies, distinguish SETUP-auth from request-auth, write fail-closed route policies, encode Simple Authentication metadata per the RSocket extension, design long streams without leaking permissions or resources, and run a Java 17+ project with `StepVerifier` tests that actually call an RSocket TCP server.

**Scope:** guides programming an RSocket TCP server on localhost. Does not assume a real Authorization Server/OIDC; the JWT section is an extension example and requires a `ReactiveJwtDecoder` from a trusted issuer. Do not mix HTTP 401/403 status codes into the RSocket TCP protocol.

## 2. RSocket interaction models and permission checkpoints

```text
Client                                       RSocket Server
  |                                               |
  |--- SETUP(auth metadata, connection prefs) --->|
  |<-- connection accepted / ERROR ---------------|
  |                                               |
  |--- REQUEST_RESPONSE(route, data) ------------>|
  |<-- PAYLOAD(result) / ERROR --------------------|
  |                                               |
  |--- REQUEST_STREAM(route) --------------------->|
  |<-- PAYLOAD #1 ---------------------------------|
  |<-- PAYLOAD #2 ---------------------------------|
  |--- REQUEST_N (demand) ------------------------>|
  |--- CANCEL (when caller stops) ---------------->|
  |                                               |
  |--- FIRE_AND_FORGET(route, data) -------------->|
  |                                               |
  |<============= long-lived connection =========>|
```

| Frame / interaction type | Characteristics | Security question |
| --- | --- | --- |
| `SETUP` | Initializes a connection | Which principal is allowed to open a connection? |
| Request-response | 1 request, at most 1 response | Is calling this route permitted? |
| Fire-and-forget | Sends data, does not wait for a business response | How to block side effects before processing? |
| Request-stream | One request triggers multiple PAYLOADs | Does the user remain authorized to receive data throughout the stream? |
| Request-channel | Client and server exchange multiple elements | What per-request authentication and per-element validation are needed? |
| `METADATA_PUSH` | New metadata on an existing connection | Must not treat unverified metadata as a principal |
| `REQUEST_N`, `CANCEL` | Backpressure, cancellation | Are resources released and publishers stopped when no subscriber remains? |

### 2.1. An RSocket route is not an HTTP path

A responder with:

```java
@MessageMapping("profile.me")
public Mono<String> whoAmI() {
    return Mono.just("response");
}
```

is routed via **RSocket routing metadata**, not `GET /profile.me`. This is an illustrative method, not a standalone compilable file.

HTTP configuration:

```java
http.authorizeExchange(ex ->
        ex.pathMatchers("/profile.me").authenticated());
```

**does not replace** `rsocket.authorizePayload(...)` for RSocket TCP routes. An application with both WebFlux REST and RSocket must configure two separate security boundaries.

### 2.2. Metadata is not completed authentication

RSocket composite metadata contains entries with MIME types such as route, authentication, and tracing. A `UsernamePasswordMetadata` is a credential supplied for the server to verify, **not an authenticated principal**. A JSON string in data like `{"user":"admin","role":"ADMIN"}` does not grant ADMIN privileges either.

Spring Security's RSocket layer uses a decoder/converter and `ReactiveAuthenticationManager` to verify credentials, then places `Authentication` into the Reactor Context. Handlers/authorization should only trust the `Authentication` coming from the security layer, never assigning it directly from data, route variables, or unverified metadata.

## 3. Distinguishing the three required components

### 3.1. `@EnableRSocketSecurity`

```java
@Configuration
@EnableRSocketSecurity
public class SecurityConfig {
    // RSocket Security beans.
}
```

Annotation in package `org.springframework.security.config.annotation.rsocket.EnableRSocketSecurity`. It enables configuration/security support rather than automatically providing TLS, JWT issuer trust, route permissions, or network ACLs. If you only add the annotation and see the server accepting connections, that does not prove private routes are protected.

### 3.2. `RSocketSecurity`

Builder in `org.springframework.security.config.annotation.rsocket.RSocketSecurity`. You use:

```java
rsocket
    .authorizePayload(authz -> authz
        .setup().permitAll()
        .route("public.ping").permitAll()
        .route("admin.ping").hasRole("ADMIN")
        .route("private.greet").authenticated()
        .route("ticks.stream").authenticated()
        .anyRequest().denyAll()
        .anyExchange().permitAll())
    .simpleAuthentication(Customizer.withDefaults());

PayloadSocketAcceptorInterceptor interceptor = rsocket.build();
```

This is a snippet inside a `@Bean` method; the full project is in section 7. Meaning:

1. `setup().permitAll()` allows establishing a connection without a principal. **Does not** mean every route is public.
2. Route `public.ping` allows anonymous requests.
3. Route `admin.ping` requires `ROLE_ADMIN`, obtained from server-side authorities, not from uploaded JSON.
4. Routes `private.greet` and `ticks.stream` require a verified `Authentication`.
5. `anyRequest().denyAll()` blocks requests that do not match the route allow-list, even if a new handler is accidentally added.
6. `anyExchange().permitAll()` is a fallback for exchanges **that are not requests with routing metadata**, such as subsequent parts of a stream; it does not mean opening matched routes publicly.
7. `simpleAuthentication(...)` enables username/password authentication using **RSocket Simple Authentication metadata**.
8. Rules are applied **in order**; only the first matching rule takes effect.

**Dangerous mistake:** placing `anyRequest().permitAll()` or `anyExchange().permitAll()` before the ADMIN rule can shadow subsequent rules. Place specific routes before fallbacks.

### 3.3. `SocketAcceptorInterceptor` and the bridge

At the RSocket Java plugin layer, `SocketAcceptorInterceptor` intercepts accepting an RSocket connection. Spring Security provides **`SecuritySocketAcceptorInterceptor`** to connect this plugin layer with the security payload interceptors. `RSocketSecurity.build()` itself returns **`PayloadSocketAcceptorInterceptor`**, not a Spring HTTP `WebFilter`.

```text
RSocketServer
     |
     v
SocketAcceptorInterceptor
     |
     v
SecuritySocketAcceptorInterceptor
     |
     v
PayloadSocketAcceptorInterceptor (from RSocketSecurity.build)
     |
     +--> AuthenticationPayloadInterceptor
     |        +--> ReactiveAuthenticationManager
     |
     +--> AuthorizationPayloadInterceptor
              +--> authorizePayload rules
     |
     v
RSocketMessageHandler -> @MessageMapping -> Mono/Flux
```

The diagram shows logical responsibilities; the internal call stack may vary by version. The key point is that the *plugin acceptor* and *payload authentication/authorization* are two connected layers.

**With Spring Boot:** when `spring-security-rsocket` and RSocket infrastructure are auto-configured, Boot registers `SecuritySocketAcceptorInterceptor` via `RSocketSecurityAutoConfiguration`. Do not add the **same interceptor** again using a manual customizer.

**Without Boot auto-config or when creating an RSocket server manually:** you can attach it manually:

```java
@Bean
RSocketServerCustomizer rsocketSecurityHook(
        SecuritySocketAcceptorInterceptor security) {
    return server -> server.interceptors(
            registry -> registry.forSocketAcceptor(security));
}
```

This snippet is for systems **without** the auto-registered bridge and is not part of the Boot demo below. Corresponding imports are `org.springframework.boot.rsocket.server.RSocketServerCustomizer` and `org.springframework.security.rsocket.core.SecuritySocketAcceptorInterceptor`.

Registering twice easily causes duplicate auditing, duplicate authentication, ordering bugs, and increased latency. Merely having a `PayloadSocketAcceptorInterceptor` bean is not enough either: it must actually be attached to the RSocket acceptor path and verified through integration tests.

## 4. Authentication at SETUP vs. per-request

### 4.1. Authentication at SETUP

A mobile app has a dedicated connection for Alice. The client sends credentials in `SETUP`:

```text
SETUP(username=alice, password=...)
      |
      v
Server verifies Alice
      |
      v
private.greet -> "hello alice"
```

Once credentials are verified, the connection context can support subsequent requests. This approach makes sense when **one connection corresponds to one principal/service identity**.

**Warning:** SETUP authentication does not automatically revalidate the password/JWT token on every long-running PAYLOAD. When a user logs out, permissions are revoked, a password changes, or a JWT expires, you must define when to **close the connection, reauthenticate, cap stream lifetime, or cancel streams** per your threat model.

### 4.2. Per-request authentication

A web backend often shares one connection to call an RSocket service on behalf of many people:

```text
Shared RSocket connection
    +-- Request for Alice -> Alice credential metadata
    +-- Request for Bob   -> Bob credential metadata
    +-- Request for Carol -> Carol credential metadata
```

In that case, do not use a single SETUP token of Alice for all users, to avoid cross-user access. The client attaches per-request metadata, and Spring Security verifies it in `AuthenticationPayloadInterceptor`.

A stronger variant: use SETUP credentials for a **service with ROLE_SETUP** to control who can connect, while per-request credentials represent the end-user identity. You must test semantics when both SETUP and request metadata are present; do not assume a request token is allowed to override all SETUP permissions.

### 4.3. Checking SETUP itself

If only trusted services are allowed to connect, you can configure:

```java
rsocket.authorizePayload(authz -> authz
        .setup().hasRole("SETUP")
        .route("private.greet").authenticated()
        .anyRequest().denyAll()
        .anyExchange().permitAll());
```

**This is an alternative policy**, not combined with the `setup().permitAll()` demo. With `hasRole("SETUP")`, the client must send verified information at SETUP; it cannot connect anonymously and then use per-request auth to bypass the setup check. `ROLE_SETUP` must be granted by the server-side manager, not self-declared by the client.

### 4.4. Simple Authentication metadata

The Simple Authentication extension uses the MIME type:

```java
MimeType authMime = MimeTypeUtils.parseMimeType(
        WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());
```

The client adds `UsernamePasswordMetadata` using `SimpleAuthenticationEncoder`. It **does not** use HTTP Basic's `Authorization: Basic` header and **does not encrypt passwords on the transport**. On real networks, you must use TLS/mTLS, certificate verification, and secrets management.

It can be sent on the connection:

```java
RSocketRequester.builder()
        .rsocketStrategies(b -> b.encoder(new SimpleAuthenticationEncoder()))
        .setupMetadata(
                new UsernamePasswordMetadata("alice", "alice-pass"),
                authMime)
        .tcp("127.0.0.1", 7000);
```

Or on each request from a shared requester:

```java
requester.route("private.greet")
        .metadata(
                new UsernamePasswordMetadata("alice", "alice-pass"),
                authMime)
        .retrieveMono(String.class);
```

The snippets above require imports, a requester, and a real server; complete code appears in sections 7/8.

## 5. RSocket authorization: setup, route, request, stream

| RSocket exchange | Rule | Expected |
| --- | --- | --- |
| Anonymous SETUP | `.setup().permitAll()` | Connection accepted |
| Anonymous `public.ping` | `.route(...).permitAll()` | Returns `pong` |
| Anonymous `private.greet` | `.authenticated()` | RSocket error |
| Authenticated Alice `private.greet` | `.authenticated()` | Returns `hello alice` |
| Authenticated Alice `admin.ping` | `.hasRole("ADMIN")` | RSocket error |
| Authenticated admin `admin.ping` | `.hasRole("ADMIN")` | Returns `admin-ok` |
| Authenticated `ticks.stream` | `.authenticated()` | Starts `Flux` |
| `internal.debug` (unlisted route) | `.anyRequest().denyAll()` | RSocket error |
| Other exchanges without request route metadata | `.anyExchange().permitAll()` | Not used to open public request routes |

**There is no default HTTP 401/403** on RSocket TCP. Authentication failure and authorization denial are propagated via Reactor `onError`/RSocket Error frame, which may be different exceptions. When running RSocket-over-WebSocket, the HTTP handshake and post-connection RSocket errors are two separate layers.

### 5.1. `hasRole` and `hasAuthority`

`hasRole("ADMIN")` normally requires `ROLE_ADMIN`; this role must come from `ReactiveAuthenticationManager`, the user store, or a verified JWT-to-authorities converter, never from raw metadata. With JWT, scopes are often converted into authorities like `SCOPE_stream.read`; if using `hasAuthority`, ensure that mapping actually exists and has been verified.

### 5.2. Do not forget the fallback

If there is a new handler `@MessageMapping("internal.debug")` that you do not want clients to call, `.anyRequest().denyAll()` provides fail-closed protection. Do not prove the fallback by calling a nonexistent route: a route without a handler errors out anyway. The test suite will create an **existing handler** and prove it is blocked by the `denyAll` rule.

## 6. The long-stream problem

If a request-stream has started with an authorized user, subsequent PAYLOADs do not automatically re-run the entire authentication/authorization DSL for each item. Suppose the user is locked out after 15 minutes while the stream remains open for hours; data can continue to be emitted if the application does not check revocation/expiry separately.

Evaluation:

1. Limit stream lifetime/lease by data type.
2. Respect `REQUEST_N` and `CANCEL`; do not use unbounded buffers.
3. Close or proactively cancel when a user logs out/is revoked if the business requires immediate revocation.
4. Consider per-message tenant/owner checks in request-channel and domain services.
5. Limit connection counts, concurrent streams, frame sizes, payload sizes, token sizes, and rates.
6. Evaluate reconnect/resumption: do not implicitly trust old credentials after reconnecting.
7. Record timeout/error/cancel metrics without logging raw auth metadata, JWTs, or passwords.
8. Do not `block()` or fire-and-forget `subscribe()` inside `@MessageMapping`.
9. Use `Flux` with cancellation cleanup (`doFinally`, `usingWhen`, resource lifecycle).
10. Ensure one user never uses another user's principal on a shared connection.

## 7. Complete Java 17+ Spring Boot RSocket TCP project

The demo runs RSocket TCP on `localhost:7000`, with five handlers:

- `public.ping` returns **pong** without credentials.
- `private.greet` returns **hello alice** or `hello admin` based on the verified principal.
- `admin.ping` is ADMIN only, returning **admin-ok**.
- `ticks.stream` returns five elements **tick-1 through tick-5**.
- `internal.debug` has a real handler but **is blocked by denyAll** because it is not allow-listed.

Local demo users:
- `alice / alice-pass` has `ROLE_USER`.
- `admin / admin-pass` has `ROLE_USER` and `ROLE_ADMIN`.

**There is no real Identity Provider and no HTTP Basic.** Demo passwords are for localhost only. Production must use TLS and a proper user store/IdP.

### 7.1. Directory structure

```text
rsocket-security-lab/
├── settings.gradle
├── build.gradle
├── src/main/resources/application.yml
├── src/main/java/example/rsocket/RSocketSecurityApplication.java
├── src/main/java/example/rsocket/RSocketSecurityConfig.java
├── src/main/java/example/rsocket/DemoRSocketController.java
├── src/main/java/example/rsocket/RSocketClientDemo.java
└── src/test/java/example/rsocket/RSocketSecurityIntegrationTest.java
```

### 7.2. settings.gradle

```groovy
rootProject.name = 'rsocket-security-lab'
```

### 7.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
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
    implementation 'org.springframework.boot:spring-boot-starter-rsocket'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-rsocket'
    implementation 'org.springframework.security:spring-security-messaging'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.register('runDemoClient', JavaExec) {
    classpath = sourceSets.main.runtimeClasspath
    mainClass = 'example.rsocket.RSocketClientDemo'
}
```

Dependency `spring-boot-starter-rsocket` provides the server/transport/`RSocketRequester`. `spring-security-rsocket` provides the DSL/interceptors/security metadata; `spring-boot-starter-security` supports user/password managers. `spring-security-messaging` supports extended messaging security features. `spring-boot-starter-web` (Servlet MVC) is not needed for a standalone TCP server. The Boot BOM selects compatible Spring Security/Reactor versions.

### 7.4. application.yml

```yaml
spring:
  application:
    name: rsocket-security-lab
  rsocket:
    server:
      transport: tcp
      address: 127.0.0.1
      port: 7000
```

Binding to loopback avoids exposing Simple Authentication over unencrypted TCP. This port **is not HTTP**: an HTTP `curl` command to 7000 does not simulate an RSocket client.

### 7.5. RSocketSecurityApplication.java

```java
package example.rsocket;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RSocketSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                RSocketSecurityApplication.class, args);
    }
}
```

### 7.6. RSocketSecurityConfig.java

```java
package example.rsocket;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.rsocket.EnableRSocketSecurity;
import org.springframework.security.config.annotation.rsocket.RSocketSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.rsocket.core.PayloadSocketAcceptorInterceptor;

@Configuration
@EnableRSocketSecurity
public class RSocketSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService(
            PasswordEncoder encoder) {

        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build();

        return new MapReactiveUserDetailsService(alice, admin);
    }

    @Bean
    PayloadSocketAcceptorInterceptor rsocketInterceptor(
            RSocketSecurity rsocket) {

        return rsocket
                .authorizePayload(authz -> authz
                        .setup().permitAll()
                        .route("public.ping").permitAll()
                        .route("admin.ping").hasRole("ADMIN")
                        .route("private.greet").authenticated()
                        .route("ticks.stream").authenticated()
                        .anyRequest().denyAll()
                        .anyExchange().permitAll())
                .simpleAuthentication(Customizer.withDefaults())
                .build();
    }
}
```

**Source explanation:**

1. `@EnableRSocketSecurity` enables RSocket Security, not HTTP Security.
2. The `RSocketSecurity` bean is injected by Spring into the method.
3. `build()` returns **PayloadSocketAcceptorInterceptor**, compatible with the Spring Boot auto-registration bridge.
4. `setup().permitAll()` is an intentional policy for this demo; private routes still require `Authentication`.
5. The admin rule uses `hasRole("ADMIN")`, corresponding to `ROLE_ADMIN` provided by `UserDetailsService`.
6. `anyRequest().denyAll()` blocks routes without a rule, including `internal.debug`.
7. `anyExchange().permitAll()` applies to exchanges not matched by preceding rules and does not break the admin rule when placed last.
8. `simpleAuthentication` authenticates `UsernamePasswordMetadata`, not an HTTP Basic header.
9. There is no manual `RSocketServerCustomizer` bean in this Boot project; avoid double-registration.
10. Passwords are BCrypt-hashed in the in-memory user store; do not use demo credentials in production.
11. No permissions are taken directly from unverified user input.

### 7.7. DemoRSocketController.java

```java
package example.rsocket;

import java.time.Duration;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class DemoRSocketController {

    @MessageMapping("public.ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @MessageMapping("private.greet")
    public Mono<String> greet() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName)
                .map(name -> "hello " + name);
    }

    @MessageMapping("admin.ping")
    public Mono<String> admin() {
        return Mono.just("admin-ok");
    }

    @MessageMapping("ticks.stream")
    public Flux<String> ticks() {
        return Flux.range(1, 5)
                .delayElements(Duration.ofMillis(40))
                .map(i -> "tick-" + i);
    }

    // Real handler, but blocked by anyRequest().denyAll().
    @MessageMapping("internal.debug")
    public Mono<String> debug() {
        return Mono.just("must-not-be-reachable");
    }
}
```

`@MessageMapping` is an RSocket route, not HTTP's `@GetMapping`. The `greet` handler reads **ReactiveSecurityContextHolder** populated by the security pipeline; it does not parse metadata or manually attach `Authentication`. In the demo, a finite 5-item `Flux` makes verification easy for learners; real streams may last for hours and require expiry/cancel/revoke policies.

### 7.8. RSocketClientDemo.java

```java
package example.rsocket;

import java.time.Duration;
import java.util.List;

import io.rsocket.metadata.WellKnownMimeType;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.security.rsocket.metadata.SimpleAuthenticationEncoder;
import org.springframework.security.rsocket.metadata.UsernamePasswordMetadata;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;

public final class RSocketClientDemo {

    private static final MimeType AUTH_MIME =
            MimeTypeUtils.parseMimeType(
                    WellKnownMimeType
                            .MESSAGE_RSOCKET_AUTHENTICATION.getString());

    public static void main(String[] args) {
        RSocketRequester requester = RSocketRequester.builder()
                .rsocketStrategies(b ->
                        b.encoder(new SimpleAuthenticationEncoder()))
                .setupMetadata(
                        new UsernamePasswordMetadata(
                                "alice", "alice-pass"),
                        AUTH_MIME)
                .tcp("127.0.0.1", 7000);

        try {
            String pong = requester.route("public.ping")
                    .retrieveMono(String.class)
                    .block(Duration.ofSeconds(5));

            String greeting = requester.route("private.greet")
                    .retrieveMono(String.class)
                    .block(Duration.ofSeconds(5));

            List<String> ticks = requester.route("ticks.stream")
                    .retrieveFlux(String.class)
                    .collectList()
                    .block(Duration.ofSeconds(5));

            System.out.println(pong);
            System.out.println(greeting);
            System.out.println(ticks);
        }
        finally {
            requester.dispose();
        }
    }
}
```

`SimpleAuthenticationEncoder` and `UsernamePasswordMetadata` encode metadata according to the RSocket MIME extension. The password is sent at SETUP, not via an HTTP Basic Authorization header.

**Reactor note:** CLI `main()` runs synchronously, so using `.block(Duration)` to print results at this boundary is acceptable. **Do not** copy `.block()` into an RSocket handler or onto the Netty event loop.

### 7.9. Running the sample

In terminal 1:

```bash
gradle bootRun
```

In terminal 2:

```bash
gradle runDemoClient
```

**Expected** output:

```text
pong
hello alice
[tick-1, tick-2, tick-3, tick-4, tick-5]
```

If the server is not running or the port is wrong, you will get a transport error. If the password is wrong or permissions are missing, you will get an RSocket error. This is expected output derived from the code, **not a claim that Gradle was executed during the authoring session**.

## 8. Real integration tests with RSocketRequester and StepVerifier

Instead of mocking the entire security layer, the test suite creates an `RSocketRequester` connecting to a **real RSocket server started by Spring Boot test**, using user/password fixtures, route permissions, and payloads. With `spring.rsocket.server.port=0`, the server receives a random port and `@LocalRSocketServerPort` injects the actual port into the test.

All tests create a new Builder/requester per identity; `RSocketRequester.Builder` is stateful and should not be reused as a mutable builder to switch SETUP credentials between Alice and Bob.

### 8.1. RSocketSecurityIntegrationTest.java

```java
package example.rsocket;

import java.time.Duration;

import io.rsocket.metadata.WellKnownMimeType;
import org.junit.jupiter.api.Test;
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
class RSocketSecurityIntegrationTest {

    private static final MimeType AUTH_MIME =
            MimeTypeUtils.parseMimeType(
                    WellKnownMimeType
                            .MESSAGE_RSOCKET_AUTHENTICATION.getString());

    @LocalRSocketServerPort
    int port;

    private RSocketRequester client(String username, String password) {
        RSocketRequester.Builder builder =
                RSocketRequester.builder()
                        .rsocketStrategies(s ->
                                s.encoder(new SimpleAuthenticationEncoder()));

        if (username != null) {
            builder.setupMetadata(
                    new UsernamePasswordMetadata(username, password),
                    AUTH_MIME);
        }

        return builder.tcp("127.0.0.1", port);
    }

    private Mono<String> request(
            String username, String password, String route) {
        RSocketRequester requester = client(username, password);
        return requester.route(route).retrieveMono(String.class)
                .doFinally(signal -> requester.dispose());
    }

    private Flux<String> stream(String username, String password) {
        RSocketRequester requester = client(username, password);
        return requester.route("ticks.stream")
                .retrieveFlux(String.class)
                .doFinally(signal -> requester.dispose());
    }

    @Test
    void anonymousSetupCanCallPublicPing() {
        StepVerifier.create(
                request(null, null, "public.ping"))
                .expectNext("pong")
                .expectComplete()
                .verify(Duration.ofSeconds(10));
    }

    @Test
    void privateGreetRejectsAnonymous() {
        StepVerifier.create(
                request(null, null, "private.greet"))
                .expectError()
                .verify(Duration.ofSeconds(10));
    }

    @Test
    void aliceSetupCredentialsAreVerified() {
        StepVerifier.create(
                request("alice", "alice-pass", "private.greet"))
                .expectNext("hello alice")
                .expectComplete()
                .verify(Duration.ofSeconds(10));
    }

    @Test
    void adminRoleCanCallAdmin() {
        StepVerifier.create(
                request("admin", "admin-pass", "admin.ping"))
                .expectNext("admin-ok")
                .expectComplete()
                .verify(Duration.ofSeconds(10));
    }

    @Test
    void aliceCannotCallAdmin() {
        StepVerifier.create(
                request("alice", "alice-pass", "admin.ping"))
                .expectError()
                .verify(Duration.ofSeconds(10));
    }

    @Test
    void wrongSetupPasswordFails() {
        StepVerifier.create(
                request("alice", "wrong", "private.greet"))
                .expectError()
                .verify(Duration.ofSeconds(10));
    }

    @Test
    void perRequestCredentialsWorkAfterAnonymousSetup() {
        RSocketRequester requester = client(null, null);
        try {
            Mono<String> response =
                    requester.route("private.greet")
                            .metadata(
                                    new UsernamePasswordMetadata(
                                            "alice", "alice-pass"),
                                    AUTH_MIME)
                            .retrieveMono(String.class);

            StepVerifier.create(response)
                    .expectNext("hello alice")
                    .expectComplete()
                    .verify(Duration.ofSeconds(10));
        }
        finally {
            requester.dispose();
        }
    }

    @Test
    void wrongPerRequestPasswordFails() {
        RSocketRequester requester = client(null, null);
        try {
            Mono<String> response =
                    requester.route("private.greet")
                            .metadata(
                                    new UsernamePasswordMetadata(
                                            "alice", "wrong"),
                                    AUTH_MIME)
                            .retrieveMono(String.class);

            StepVerifier.create(response)
                    .expectError()
                    .verify(Duration.ofSeconds(10));
        }
        finally {
            requester.dispose();
        }
    }

    @Test
    void anonymousCannotCallAdmin() {
        StepVerifier.create(
                request(null, null, "admin.ping"))
                .expectError()
                .verify(Duration.ofSeconds(10));
    }

    @Test
    void authenticatedUserCanOpenStream() {
        StepVerifier.create(
                stream("alice", "alice-pass"))
                .expectNext(
                        "tick-1", "tick-2", "tick-3",
                        "tick-4", "tick-5")
                .expectComplete()
                .verify(Duration.ofSeconds(10));
    }

    @Test
    void anonymousCannotOpenStream() {
        StepVerifier.create(
                stream(null, null))
                .expectError()
                .verify(Duration.ofSeconds(10));
    }

    @Test
    void takeTwoCancelsTheStream() {
        StepVerifier.create(
                stream("alice", "alice-pass").take(2))
                .expectNext("tick-1", "tick-2")
                .expectComplete()
                .verify(Duration.ofSeconds(10));
    }

    @Test
    void unknownButExistingHandlerIsDenied() {
        StepVerifier.create(
                request("admin", "admin-pass", "internal.debug"))
                .expectError()
                .verify(Duration.ofSeconds(10));
    }

    @Test
    void separateConnectionsDoNotSharePrincipals() {
        StepVerifier.create(
                request("alice", "alice-pass", "private.greet"))
                .expectNext("hello alice")
                .expectComplete()
                .verify(Duration.ofSeconds(10));

        StepVerifier.create(
                request("admin", "admin-pass", "private.greet"))
                .expectNext("hello admin")
                .expectComplete()
                .verify(Duration.ofSeconds(10));
    }
}
```

### 8.2. Running tests

```bash
gradle test
```

**Expected:** 14 tests PASS when JDK, Gradle, and dependencies are compatible. This is a design expectation, **not an actual execution result from the authoring session**.

| Test | Expected result | Verification |
| --- | --- | --- |
| Anonymous setup calls public | `pong` | SETUP permitAll + public rule |
| Anonymous into private | Error | Authenticated rule |
| Alice setup with right password | `hello alice` | Simple Auth actually verifies credentials |
| Admin setup right | `admin-ok` | `ROLE_ADMIN` from server |
| Alice into admin | Error | Authorization blocks user lacking role |
| Wrong password SETUP | Error | Does not just read username |
| Request metadata for Alice | `hello alice` | Per-request authentication |
| Request metadata wrong password | Error | Bad credentials do not grant access |
| Anonymous into admin | Error | Setup `permitAll` does not bypass route |
| Alice opens stream | `tick-1..tick-5` | Stream request has authorization |
| Anonymous opens stream | Error | Private stream is not public |
| `take(2)` | Two items then complete | Subscriber cancellation |
| `internal.debug` | Error | `denyAll` blocks real handler |
| Two connections | Correct Alice/Admin | Identity isolation |

### 8.3. Why not assert HTTP 401/403?

RSocket TCP returns data per protocol; when authn/authz fails it sends an **RSocket Error frame** and Reactor `onError`. HTTP status codes apply only to the HTTP handshake (when using RSocket-over-WebSocket) and do not directly represent RSocket request errors inside the connection.

`expectError()` indicates the request did not succeed; to distinguish security errors from network timeouts in production, assert specific **RSocket error types/codes** per dependency version, along with safe server-side logs. Do not rely solely on string exception messages that can change.

### 8.4. Why not block inside the handler?

Correct in `@MessageMapping`:

```java
return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .map(name -> "hello " + name);
```

Wrong on the Netty event loop:

```java
String name = ReactiveSecurityContextHolder.getContext()
        .block()
        .getAuthentication().getName();
```

The second snippet is an antipattern for explanation only; do not use it in project source. Reactive Context can migrate across threads, so do not use thread-local `SecurityContextHolder` as is default in Servlet either. Return `Mono`/`Flux` so the framework manages subscription, errors, and cancellation.

## 9. Replacing Simple Authentication with JWT Bearer

If your organization uses OAuth2/OIDC, Spring Security RSocket supports `.jwt(Customizer.withDefaults())`, using a trusted `ReactiveJwtDecoder`.

Alternative configuration option:

```java
@Bean
PayloadSocketAcceptorInterceptor rsocketJwtSecurity(
        RSocketSecurity rsocket) {
    return rsocket
            .authorizePayload(authz -> authz
                    .setup().permitAll()
                    .route("public.ping").permitAll()
                    .route("private.greet").authenticated()
                    .anyRequest().denyAll()
                    .anyExchange().permitAll())
            .jwt(Customizer.withDefaults())
            .build();
}
```

This is a **replacement option** for the Simple Authentication bean; do not blindly add two beans and two interceptors doing the same job to the application. You need a **`ReactiveJwtDecoder` bean** verifying issuer, JWS signature, expiry, not-before, and the service's **audience**. When scopes are needed, map them to verified authorities such as `SCOPE_xxx` per policy and check tenant/owner in the business layer.

The client uses `BearerTokenMetadata` at SETUP or per request:

```java
// Snippet only: bearerValue must be issued by a trusted IdP.
BearerTokenMetadata bearer = new BearerTokenMetadata(bearerValue);

RSocketRequester requester = RSocketRequester.builder()
        .setupMetadata(bearer, AUTH_MIME)
        .tcp("127.0.0.1", 7000);
```

This section requires imports/decoder/real token and appropriate TLS; it **is not a standalone runnable Java file**. Do not Base64URL-decode a JWT yourself and trust `sub`/`role` before verification. Do not use an OIDC ID token as an access token just because the token has a valid signature.

**Stream expiry:** A JWT can expire or be revoked while a request-stream is still emitting data; checking when opening the stream does not automatically mean re-authenticating on every item. If risk requires immediate revocation, you must proactively cancel/revalidate/limit stream lifetime.

## 10. Customizing SocketAcceptorInterceptor/PayloadInterceptor

When Boot auto-config is active, do not re-attach **`SecuritySocketAcceptorInterceptor`** manually. If the application uses a self-hosted RSocket server or other protocol interceptors, plan ordering and responsibilities clearly.

`RSocketSecurity.addPayloadInterceptor(custom)` supports adding a payload interceptor when the standard DSL does not suffice. Per the Javadoc, a custom `PayloadInterceptor` needs appropriate `Ordered`/`@Order` to avoid misordered interaction with `AuthenticationPayloadInterceptor` and `AuthorizationPayloadInterceptor`.

Do not use a custom interceptor to fake an authenticated principal by reading metadata and assigning authorities. If you must authenticate a new API key/HMAC scheme, implement a real credential converter and `ReactiveAuthenticationManager` that verifies credentials, restricts routes, and adds anti-replay, rate limiting, and key rotation.

**Be careful with double-registration:**

- Duplicate authentication/authorization can run twice.
- Metrics/audit events can be duplicated.
- `SecurityContext` and error handling become hard to predict.
- Connections get rejected even though the policy appears to permit them.
- Per-payload overhead increases on long streams.
- Tests that only check for bean existence will not detect a duplicated bridge: you must test actual behavior.

## 11. Common pitfalls

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Enabling `@EnableRSocketSecurity` without configuring route policies | Wrong protection | `RSocketSecurity.authorizePayload` |
| Missing `spring-security-rsocket` | Missing API/auto-configuration | Add dependency |
| Thinking `build()` directly returns an RSocket HTTP `WebFilter` | Layer confusion | `PayloadSocketAcceptorInterceptor` |
| Manual registration while Boot auto-registers | Double security layer | Attach the bridge once |
| Using `ServerHttpSecurity` for RSocket TCP | Routes left unprotected | `RSocketSecurity`, not HTTP matchers |
| SETUP `permitAll` and skipping route rules | Routes left open unintentionally | Independent route authorization |
| Putting `anyRequest().permitAll()` before admin | Shadows admin rule | Specific rules before fallback |
| Omitting trailing `denyAll` | New handlers risk exposure | `anyRequest().denyAll()` |
| Using HTTP Basic header in TCP | Auth does not run | Simple RSocket metadata |
| Sending username/password over public TCP | Credential leakage | TLS/mTLS |
| Reusing Alice's SETUP identity for Bob | Cross-user access | Per-request auth/connection isolation |
| Treating raw metadata as an authenticated user | Authentication bypass | Verified `Authentication` |
| Enabling JWT without a decoder | Missing verification | `ReactiveJwtDecoder` with issuer/aud |
| Using a JWT ID token instead of an access token | Token confusion | Check token profile |
| Expecting HTTP 403 on RSocket TCP | Wrong test assertions | RSocket Error/`onError` |
| Reusing a mutable Builder to switch users | Mixed-up credential metadata | Separate Builder |
| Not disposing the requester | Connection leak | Lifecycle cleanup |
| `.block()` inside a handler | Blocks event loop | Nonblocking `Mono`/`Flux` |
| Fire-and-forget `.subscribe()` inside a request | Detached/ignored errors | Return the publisher |
| Overly long stream without timeout | Stale rights/resource leak | TTL/revalidation/cancel |
| Unbounded buffer or ignoring `REQUEST_N` | Memory/DoS | Backpressure, quotas |
| Skipping tenant/record permission checks | IDOR | Domain-level authorization |
| Logging raw SETUP metadata | Password/token leak | Redact, restrict logs |

## 12. Production deployment checklist

1. Use TLS/mTLS when RSocket TCP goes beyond localhost; WSS if transporting through a browser.
2. Have `@EnableRSocketSecurity` and one `PayloadSocketAcceptorInterceptor` bean.
3. Verify the `SecuritySocketAcceptorInterceptor` bridge is attached **once** to the RSocket server.
4. Define SETUP rules clearly; do not treat `permitAll` SETUP as allowing all requests.
5. All private/admin routes have allow rules before the `denyAll` fallback.
6. Credentials are verified by `ReactiveAuthenticationManager` or `ReactiveJwtDecoder`.
7. Do not turn client-declared roles in data/route/metadata into authorities.
8. On shared connections, send per-request credentials and isolate principal identities.
9. JWTs must be checked for issuer, audience, expiry, signature, token use, and scopes.
10. Limit max connections, frame/payload sizes, concurrent streams, and request rates.
11. Monitor stream cancellation, backpressure, timeouts, and cleanup after disconnect.
12. Have token expiry/revocation policies for long streams; do not assume SETUP auth is permanent.
13. Write audit logs by verified principal, avoiding raw token/password logs.
14. Test public SETUP, private denied, admin denied/allowed, and wrong credentials.
15. Test per-request metadata, open and cancelled streams, and unknown existing routes.
16. Distinguish RSocket authentication failure, authorization denial, and transport failure.
17. Test multiple users and multi-tenants; never misuse SETUP credentials.
18. Do not block the Netty event loop, and do not manually subscribe inside `@MessageMapping`.
19. Check reconnect/resumption and TLS certificate validation at the edge.
20. After upgrading Spring Boot/Security, re-check RSocket auto-config and Javadocs.

## 13. Self-assessment exercises

1. Does `@EnableRSocketSecurity` automatically create TLS? — No.
2. What does `RSocketSecurity.build()` return? — `PayloadSocketAcceptorInterceptor`.
3. How do `SocketAcceptorInterceptor` and `PayloadSocketAcceptorInterceptor` differ? — Plugin acceptor vs. payload security chain.
4. Does Boot automatically attach the bridge when the required dependencies are present? — Yes.
5. Should you add a second manual customizer? — No.
6. Does SETUP `permitAll` mean all routes are public? — No.
7. Why are route rules declared in order? — The first matching rule is used.
8. What is `anyRequest().denyAll()` for? — Blocking unknown requests fail-closed.
9. Does `anyExchange().permitAll()` open admin publicly? — No, if placed properly at the end after matching rules.
10. Which MIME type does Simple Authentication use? — `MESSAGE_RSOCKET_AUTHENTICATION`.
11. Why doesn't Simple use an HTTP Basic header? — RSocket uses metadata with its own MIME, and there are no HTTP request headers over TCP.
12. Why is TLS needed with Simple metadata? — Passwords are not encrypted by the Simple protocol itself.
13. When are setup credentials appropriate? — Single-principal connections.
14. When is per-request auth appropriate? — Shared connections for multiple end-users.
15. Where does `ROLE_ADMIN` in the example come from? — `UserDetailsService`/verified `Authentication`.
16. Can a raw role from data be used as an authority? — No.
17. Does an RSocket TCP auth failure return HTTP 401? — No, an Error frame/`onError`.
18. Why does the test use `@LocalRSocketServerPort`? — To inject the actual random RSocket TCP port.
19. Why not reuse a mutable `RSocketRequester.Builder` across users? — SETUP credentials can get mixed up.
20. Why is testing the `internal.debug` handler important? — The handler really exists, yet must be blocked by the `denyAll` fallback.
21. Does Request-stream re-authenticate every PAYLOAD by default? — No.
22. What must be done when a user is revoked mid-stream? — Limit/revalidate/cancel per policy.
23. Why are `REQUEST_N` and `CANCEL` important? — Backpressure and cleanup.
24. Which bean type is needed when using JWT? — A trusted `ReactiveJwtDecoder`.
25. Does a positive `public.ping` test prove admin is safe? — No, negative admin tests are required.

## 14. References

- Spring Security — RSocket Security: https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html
- Spring Security 6.5 — RSocketSecurity Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/rsocket/RSocketSecurity.html
- Spring Security 6.5 — EnableRSocketSecurity: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/rsocket/EnableRSocketSecurity.html
- Spring Security — PayloadSocketAcceptorInterceptor: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/rsocket/core/PayloadSocketAcceptorInterceptor.html
- Spring Security — UsernamePasswordMetadata: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/rsocket/metadata/UsernamePasswordMetadata.html
- Spring Boot 3.5 — RSocket: https://docs.spring.io/spring-boot/3.5/reference/messaging/rsocket.html
- Spring Boot 3.5 — Application Properties: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Framework — RSocket requester/annotated responders: https://docs.spring.io/spring-framework/reference/rsocket.html
- Project Reactor — Reference: https://projectreactor.io/docs/core/release/reference/
- RSocket Protocol: https://rsocket.io/about/protocol/

**Conclusion:** With Spring Security Reactive RSocket, the right setup is `@EnableRSocketSecurity` and `RSocketSecurity` (building one `PayloadSocketAcceptorInterceptor`), wired into the RSocket server by Spring Boot via `SecuritySocketAcceptorInterceptor`/`SocketAcceptorInterceptor`. Define independent SETUP and route permissions, rule order and `denyAll` fallback, verify Simple or Bearer metadata, and apply appropriate policies for long-lived streams. Test via `RSocketRequester`/`StepVerifier`, not via HTTP `curl`/status codes; production must have TLS, reconnect/revalidation, cancellation, and resource limits.