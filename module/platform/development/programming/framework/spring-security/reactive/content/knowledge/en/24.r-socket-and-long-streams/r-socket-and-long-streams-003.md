# Authenticating RSocket with Simple Authentication or Bearer Token in Spring Security Reactive

> **Module:** Spring Security - reactive  
> **Parent topic:** RSocket and long streams  
> **Goal:** Configure RSocket security at the SETUP frame or per request, send Simple Authentication (username/password) or Bearer JWT using the proper authentication metadata, authorize RSocket routes with Spring Security, handle long streams, and test RSocket TCP directly with Java 17+.

## 1. Problem statement and target outcomes

A server accepts RSocket requests `secure.echo`, `secure.stream`, and `secure.emit`. A client can open a TCP connection and then send multiple requests over the same connection. We want to reject unauthenticated requests while allowing two ways to prove identity:

1. **Simple Authentication:** the client supplies username/password in RSocket Authentication Metadata; Spring Security verifies them using `ReactiveUserDetailsService` and a password encoder.
2. **Bearer JWT:** the client supplies an access token in authentication metadata; Spring Security uses `ReactiveJwtDecoder` to verify the signature and claims, then matches scopes/authorities against the route.

Unlike REST APIs, RSocket has SETUP, REQUEST_RESPONSE, REQUEST_STREAM, REQUEST_FNF, REQUEST_CHANNEL, PAYLOAD, REQUEST_N, and CANCEL frames. A single connection can live a long time and carry multiple concurrent streams. Security must decide **who can connect** and **who can execute each request**, without treating those two questions as the same.

In this lesson, the RSocket server runs on localhost TCP in a lab. Any real environment sending usernames/passwords or tokens must use **TLS or WSS**, redaction, and resource limits. Plaintext TCP in the example is strictly for learning on a local machine.

## 2. RSocket compared to HTTP and WebSocket

| Topic | HTTP WebFlux | RSocket |
| --- | --- | --- |
| Protocol | HTTP requests/responses | RSocket frames + metadata/payload |
| Routing | URL, HTTP method | Route in RSocket metadata |
| Credentials | Usually `Authorization`/cookie | Authentication metadata extension |
| Security DSL | `ServerHttpSecurity` | `RSocketSecurity` |
| Error response | HTTP 401/403/5xx | RSocket ERROR/frame or setup rejection |
| Long streams | SSE/WebSocket/Flux | Request-stream/request-channel with backpressure |
| Connection | Per request or HTTP connection pool | Single connection multiplexing many interactions |

**You cannot simply declare an HTTP `SecurityWebFilterChain` and assume RSocket routes are protected.** RSocket security flows through `PayloadSocketAcceptorInterceptor`; an HTTP WebSocket handshake may be protected at another layer, but RSocket request frames must still enforce their own policies.

RSocket request-response is typically read with `retrieveMono`; request-stream with `retrieveFlux`; fire-and-forget with `send()`. With fire-and-forget, the `Mono` completing upon a successful send **does not confirm** that a business transaction has committed.

## 3. Authentication at SETUP vs. per-request concepts

~~~mermaid
sequenceDiagram
    participant C as RSocket Client
    participant S as Spring RSocket Server
    participant A as Security Interceptor
    participant H as MessageMapping
    C->>S: SETUP + authentication metadata (if any)
    S->>A: Check SETUP policy
    alt Setup rejected
        A-->>C: Setup error
    else Setup accepted
        S-->>C: Connection established
        C->>S: REQUEST_RESPONSE route=secure.echo + metadata
        S->>A: Authenticate request metadata / context
        A->>A: Check matching route authorities
        alt Not allowed
            A-->>C: RSocket error
        else Allowed
            A->>H: invoke handler
            H-->>C: response payload
        end
    end
~~~

**SETUP authentication** fits when a connection always belongs to a single user or a single service: the client logs in when connecting, and subsequent requests can inherit the security context. **Per-request authentication** fits shared connections: each request carries the token/credentials of the actual principal.

Both can be combined: a workload has permission to open the connection at SETUP, while end-users have their own permissions per request. However, inheritance/override policies must be explicitly designed. Never put Alice's token in SETUP and then send Bob's requests over the same requester without per-request control, because downstream could process everything as Alice.

**Verification timing matters:** a JWT verified when opening a stream does not mean every subsequent event in the stream is automatically re-verified. See the section on expiry and revocation.

## 4. Spring RSocket security architecture

Key classes/beans:

- `@EnableRSocketSecurity` and `RSocketSecurity` from Spring Security RSocket.
- `PayloadSocketAcceptorInterceptor` created by `rsocket.build()`.
- `SecuritySocketAcceptorInterceptor` attached to the acceptor, auto-registered by Spring Boot when dependencies are right; manual integration requires `RSocketServerCustomizer`.
- `AuthenticationPayloadInterceptor` connecting the authentication converter with `ReactiveAuthenticationManager`.
- `AuthorizationPayloadInterceptor` deciding permissions by route/setup/metadata.
- `MapReactiveUserDetailsService` and `PasswordEncoder` for Simple Authentication.
- `ReactiveJwtDecoder` + validators when using JWT.
- `RSocketRequester` on the client and `@MessageMapping` on the receiver.

WebFlux HTTP and RSocket configurations can coexist, but they do not share the same filter chain. For standalone RSocket TCP, there are no HTTP 401/403 codes per frame. If an organization places an HTTP gateway in front of RSocket, the gateway defines how errors map to HTTP responses, not the default RSocket protocol.

## 5. Authentication metadata MIME type

RSocket authentication uses `WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION`:

~~~java
import io.rsocket.metadata.WellKnownMimeType;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;

MimeType authMime = MimeTypeUtils.parseMimeType(
    WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());
~~~

The MIME type determines how Spring Security reads the metadata. Clients need composite metadata when sending route + credentials together. Route name, username/password, and Bearer token are **separate** entries—do not arbitrarily merge credentials into the route or business payload.

| Sender side | Object | Encoder | Receiver Security DSL |
| --- | --- | --- | --- |
| Simple | `UsernamePasswordMetadata` | `SimpleAuthenticationEncoder` | `simpleAuthentication(...)` |
| Bearer JWT | `BearerTokenMetadata` | String metadata per RSocket extension | `jwt(...)` |

Do not pass an HTTP `Authorization: Bearer ...` header into RSocket TCP expecting the receiver to recognize it automatically. RSocket auth metadata has its own format; if the MIME type or encoder is wrong, the server cannot authenticate properly.

## 6. What is Simple Authentication, and is it HTTP Basic?

Simple Authentication sends username/password according to the RSocket Authentication Metadata Extension. It is not HTTP Basic, even though both carry two values: username and password. Spring Security has deprecated the old `basicAuthentication(...)` DSL; for the standard mechanism, use `simpleAuthentication(Customizer.withDefaults())`.

Sample receiver:

~~~java
@Bean
PayloadSocketAcceptorInterceptor rsocketInterceptor(
        RSocketSecurity rsocket) {
    rsocket.authorizePayload(authz -> authz
            .anyRequest().authenticated()
            .anyExchange().permitAll())
        .simpleAuthentication(Customizer.withDefaults());
    return rsocket.build();
}
~~~

The snippet above is a **fragment**: it must be placed inside a `@Configuration`/`@EnableRSocketSecurity` class with user details and a password policy added. In production, use an account store/IdP with rate limiting, lockout, and proper password hashing; do not hardcode passwords, and do not use `User.withDefaultPasswordEncoder()` outside demos.

Username/password are long-lived credentials. If a shared pool uses admin credentials at SETUP, all users risk receiving admin rights. Use per-request credentials or a workload identity at SETUP when connections are shared.

## 7. Bearer JWT and differences from opaque tokens

Bearer authentication metadata can carry a token string; for example, Spring Security `rsocket.jwt(...)` validates a **JWT** using `ReactiveJwtDecoder`. It does not issue tokens, does not refresh tokens, and has no default introspection for opaque random strings.

Required JWT checks:
- JWS signature using a trusted public key/JWKS and an allowlisted algorithm.
- `iss` matching the trusted issuer.
- `exp`, `nbf` within allowed clock skew.
- `aud` containing this RSocket service or allowed resource ID.
- Appropriate claim type/token purpose; **an OIDC ID Token does not replace an access token**.
- Scopes/roles at the route and owner/tenant in the domain service.

If the system actually uses OAuth2 opaque tokens, you must use a compatible custom authentication manager/introspection pipeline and test it; do not disable JWT checks or treat Base64 decoding as authentication.

## 8. Route authorization and matcher order

Illustrative DSL:

~~~java
rsocket.authorizePayload(authz -> authz
    .setup().permitAll()
    .route("secure.echo").hasRole("USER")
    .route("secure.stream").hasRole("USER")
    .route("secure.emit").hasRole("USER")
    .anyRequest().denyAll()
    .anyExchange().permitAll());
~~~

Matchers are evaluated **in order**. The rule `anyRequest().denyAll()` blocks any undeclared RSocket request route. `anyExchange().permitAll()` is a fallback for remaining exchanges, such as continuation frames without route metadata, per Spring Security guidance.

If `anyRequest().permitAll()` is placed before private routes, all requests can be permitted and subsequent checks lose effect. Do not confuse a route string with an HTTP path. With JWT, for example, use `.hasAuthority("SCOPE_messages.read")` instead of roles per your API policy.

### 8.1. Requiring permission at SETUP

If a peer needs special permission before opening a connection:

~~~java
rsocket.authorizePayload(authz -> authz
    .setup().hasRole("SETUP")
    .route("secure.echo").hasAuthority("SCOPE_messages.read")
    .anyRequest().denyAll()
    .anyExchange().permitAll());
~~~

This is a **variant configuration**. The SETUP peer needs `ROLE_SETUP`; individual requests can carry separate user credentials. Verify whether the setup identity is retained or overridden when request metadata arrives, avoiding mixing peer permissions with user permissions.

## 9. Java 17+ lab project and version limits

The project uses Spring Boot `3.3.13` and Spring Security 6.x for stable example APIs. This is a learning version whose **OSS support has ended**; new production deployments need a supported version and a review of APIs/known vulnerabilities.

~~~text
rsocket-simple-bearer/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/rsocket/
    │   │   ├── RSocketApp.java
    │   │   ├── SecuredRoutes.java
    │   │   ├── SimpleRSocketSecurityConfig.java
    │   │   ├── JwtRSocketSecurityConfig.java
    │   │   └── SimpleClient.java
    │   └── resources/application.yml
    └── test/java/demo/rsocket/
        ├── SimpleAuthRSocketTest.java
        └── JwtBearerRSocketTest.java
~~~

Two profiles `simple` and `jwt` allow using the same route controller while choosing a separate authentication mechanism. Do not enable both simultaneously in the lab because that would register two interceptors with different semantics.

### 9.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>rsocket-simple-bearer</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <properties><java.version>17</java.version></properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-rsocket</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-rsocket</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build><plugins><plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
    </plugin></plugins></build>
</project>
~~~

RSocket TCP is a separate server and does not need the HTTP Servlet starter. `spring-boot-starter-rsocket` provides RSocket messaging/Netty; `spring-security-rsocket` provides metadata security. The OAuth2 Resource Server dependency is for the JWT profile, not an Authorization Server.

### 9.2. RSocketApp.java

~~~java
package demo.rsocket;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RSocketApp {
    public static void main(String[] args) {
        SpringApplication.run(RSocketApp.class, args);
    }
}
~~~

### 9.3. application.yml

~~~yaml
spring:
  profiles:
    default: simple
  rsocket:
    server:
      transport: tcp
      port: ${RSOCKET_PORT:7000}

demo:
  rsocket:
    username: ${DEMO_RSOCKET_USER:demo}
    password: ${DEMO_RSOCKET_PASSWORD:}
  jwt:
    issuer: ${RSOCKET_JWT_ISSUER:https://issuer.example.invalid/realms/demo}
    jwks-uri: ${RSOCKET_JWKS_URI:https://issuer.example.invalid/jwks}
    audience: ${RSOCKET_JWT_AUDIENCE:messages-api}
~~~

`.invalid` is used as a placeholder; **there is no IdP there**. The `simple` profile fails fast when password is blank; the `jwt` profile only works with real issuer/JWKS URLs of a trusted IdP. Test execution can use random RSocket port `0` instead of fixed `7000`.

## 10. SecuredRoutes.java: three interaction styles

~~~java
package demo.rsocket;

import java.time.Duration;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class SecuredRoutes {

    @MessageMapping("secure.echo")
    public Mono<String> echo(String value) {
        return Mono.just("echo:" + value);
    }

    @MessageMapping("secure.stream")
    public Flux<String> stream(Integer requested) {
        int count = Math.min(5, Math.max(1, requested));
        return Flux.range(0, count)
            .delayElements(Duration.ofMillis(20))
            .map(i -> "event-" + i);
    }

    @MessageMapping("secure.emit")
    public Mono<Void> emit(String message) {
        // The lab does not write to a database or create side effects.
        return Mono.empty();
    }
}
~~~

Spring Boot creates `RSocketMessageHandler` to locate `@MessageMapping` routes, and the interceptor verifies security before the handler runs. `secure.echo` is request-response, `secure.stream` is request-stream, and `secure.emit` can use fire-and-forget.

The stream is capped at five events for the lab. Production requires per-principal/tenant quotas, message size limits, protection against stream exhaustion, cancellation, and business authorization on emitted data. Do not send a global multi-tenant `Flux` to all subscribers just because the route requires `authenticated`.

## 11. SimpleRSocketSecurityConfig.java: username/password truly verified

~~~java
package demo.rsocket;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.rsocket.EnableRSocketSecurity;
import org.springframework.security.config.annotation.rsocket.RSocketSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.rsocket.core.PayloadSocketAcceptorInterceptor;

@Configuration
@Profile("simple")
@EnableRSocketSecurity
public class SimpleRSocketSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(
            PasswordEncoder encoder,
            @Value("${demo.rsocket.username}") String username,
            @Value("${demo.rsocket.password}") String password) {
        if (password.isBlank()) {
            throw new IllegalStateException(
                "DEMO_RSOCKET_PASSWORD must be configured");
        }
        UserDetails user = User.withUsername(username)
            .password(encoder.encode(password))
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(user);
    }

    @Bean
    PayloadSocketAcceptorInterceptor simpleInterceptor(
            RSocketSecurity rsocket) {
        rsocket.authorizePayload(authz -> authz
                .setup().permitAll()
                .route("secure.echo").hasRole("USER")
                .route("secure.stream").hasRole("USER")
                .route("secure.emit").hasRole("USER")
                .anyRequest().denyAll()
                .anyExchange().permitAll())
            .simpleAuthentication(Customizer.withDefaults());
        return rsocket.build();
    }
}
~~~

**Read carefully:**
1. `@EnableRSocketSecurity` connects the RSocket Security DSL to the app.
2. `MapReactiveUserDetailsService` stores demo `UserDetails` with a BCrypt hash, not a plaintext password.
3. `setup().permitAll()` allows creating a connection without credentials, but private routes still require permissions.
4. `roles("USER")` creates authority `ROLE_USER` for `hasRole("USER")` to match.
5. `simpleAuthentication` installs the credential converter; it does not use HTTP Basic.
6. `anyRequest().denyAll()` denies request routes outside the allowlist.
7. Do not simultaneously activate the JWT profile beans; pick only one profile.

Production should use an account service, secret manager, and password policies instead of a single configured user. Passwords in metadata are only safe over TLS/WSS; never use plaintext RSocket TCP over the internet.

## 12. SimpleClient.java: sending Simple credentials at SETUP

~~~java
package demo.rsocket;

import java.time.Duration;
import java.util.List;
import io.rsocket.metadata.WellKnownMimeType;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.security.rsocket.metadata.SimpleAuthenticationEncoder;
import org.springframework.security.rsocket.metadata.UsernamePasswordMetadata;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;

public final class SimpleClient {

    private static final MimeType AUTH =
        MimeTypeUtils.parseMimeType(
            WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

    public static void main(String[] args) {
        String user = System.getenv()
            .getOrDefault("DEMO_RSOCKET_USER", "demo");
        String password = System.getenv("DEMO_RSOCKET_PASSWORD");
        if (password == null || password.isBlank()) {
            throw new IllegalStateException(
                "DEMO_RSOCKET_PASSWORD must be configured");
        }

        RSocketRequester requester = RSocketRequester.builder()
            .rsocketStrategies(s ->
                s.encoder(new SimpleAuthenticationEncoder()))
            .setupMetadata(
                new UsernamePasswordMetadata(user, password), AUTH)
            .connectTcp("127.0.0.1", 7000)
            .block(Duration.ofSeconds(10));

        if (requester == null) {
            throw new IllegalStateException("RSocket connect failed");
        }
        try {
            String echo = requester.route("secure.echo")
                .data("hello")
                .retrieveMono(String.class)
                .block(Duration.ofSeconds(10));
            List<String> events = requester.route("secure.stream")
                .data(3)
                .retrieveFlux(String.class)
                .collectList()
                .block(Duration.ofSeconds(10));
            System.out.println(echo);
            System.out.println(events);
        } finally {
            requester.rsocket().dispose();
        }
    }
}
~~~

When the password matches the server and the server is running on `localhost:7000`, expected stdout:

~~~text
echo:hello
[event-0, event-1, event-2]
~~~

**Distinction:** This is the expected output of the lab code, not a claim that the code was executed in this conversation. `RSocketRequester.builder()` supports configuring setup metadata, and `SimpleAuthenticationEncoder` encodes username/password into the authentication MIME.

At SETUP, the requester represents a specific principal. Do not reuse this requester as a singleton for multiple different users if downstream needs to authorize according to the caller of an upstream HTTP request.

## 13. Simple credentials per request

For a shared connection, attach credentials per request:

~~~java
// Snippet; requester, user, password, authMime already exist.
UsernamePasswordMetadata credential =
    new UsernamePasswordMetadata(user, password);

Mono<String> result = requester.route("secure.echo")
    .metadata(credential, authMime)
    .data("hello")
    .retrieveMono(String.class);
~~~

The requester must be built with `SimpleAuthenticationEncoder` in `RSocketStrategies`. Auth metadata must travel **with** the specific interaction; never store username/password in a global mutable variable such as `currentCredential` on a pooled requester.

On the server side, `simpleAuthentication` can process credentials at setup or per request per the extension. Configure matching/authorization rules so requests without metadata are not automatically granted access. If an endpoint truly needs to be public, add an explicit `permitAll` route before deny-all rather than opening the entire API.

## 14. JwtRSocketSecurityConfig.java: Bearer JWT on the receiver

~~~java
package demo.rsocket;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.rsocket.EnableRSocketSecurity;
import org.springframework.security.config.annotation.rsocket.RSocketSecurity;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.rsocket.core.PayloadSocketAcceptorInterceptor;

@Configuration
@Profile("jwt")
@EnableRSocketSecurity
public class JwtRSocketSecurityConfig {

    @Bean
    ReactiveJwtDecoder jwtDecoder(
            @Value("${demo.jwt.issuer}") String issuer,
            @Value("${demo.jwt.jwks-uri}") String jwksUri,
            @Value("${demo.jwt.audience}") String audience) {

        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withJwkSetUri(jwksUri)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> validators =
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                jwt -> jwt.getAudience().contains(audience)
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error("invalid_token",
                            "Wrong audience for RSocket service", null)));

        decoder.setJwtValidator(validators);
        return decoder;
    }

    @Bean
    PayloadSocketAcceptorInterceptor jwtInterceptor(
            RSocketSecurity rsocket) {

        rsocket.authorizePayload(authz -> authz
                .setup().permitAll()
                .route("secure.echo")
                    .hasAuthority("SCOPE_messages.read")
                .route("secure.stream")
                    .hasAuthority("SCOPE_messages.read")
                .route("secure.emit")
                    .hasAuthority("SCOPE_messages.write")
                .anyRequest().denyAll()
                .anyExchange().permitAll())
            .jwt(Customizer.withDefaults());

        return rsocket.build();
    }
}
~~~

**Do not only check the signature:** `withJwkSetUri` uses a trusted JWKS URI, pins `RS256` per policy, and combines issuer/time validators with an audience validator. If a real IdP uses another algorithm, choose an allowlist matching the IdP contract rather than trusting whatever algorithm the token declares.

The default JWT scope converter typically creates `SCOPE_messages.read` from `scope=messages.read` or `scp`. If the IdP issues another role claim, a corresponding converter and negative tests are needed. A token signed by the same issuer but with another service's `aud` **must be rejected**.

Do not use an OIDC ID Token as an access token for an RSocket Resource Server. Never pass a JWKS URL sent by a user request into `withJwkSetUri`, avoiding SSRF/trust injection.

## 15. BearerTokenMetadata at SETUP or per request

Both forms use `BearerTokenMetadata`:

~~~java
import io.rsocket.metadata.WellKnownMimeType;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.security.rsocket.metadata.BearerTokenMetadata;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;
import reactor.core.publisher.Mono;

MimeType authMime = MimeTypeUtils.parseMimeType(
    WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

// accessToken must be obtained by a trusted OAuth2 client for the right audience.
String accessToken = tokenFromAuthorizedClient;

// SETUP authentication: one identity for the connection.
Mono<RSocketRequester> connection = RSocketRequester.builder()
    .setupMetadata(new BearerTokenMetadata(accessToken), authMime)
    .connectTcp("127.0.0.1", 7000);

// Per-request authentication: separate identity for the interaction.
Mono<String> response = requester.route("secure.echo")
    .metadata(new BearerTokenMetadata(accessToken), authMime)
    .data("hello")
    .retrieveMono(String.class);
~~~

This is a **snippet**; variables `tokenFromAuthorizedClient` and `requester` are assumed inputs (not tokens issued inside this project); use valid OAuth2 Client Credentials/Authorization Code + token exchange depending on your trust model. Do not hardcode JWTs, do not send raw ID Tokens, and do not copy a token with the wrong audience to this service.

**Do not confuse RSocket Bearer with HTTP:** the metadata holds the token string; the client does not add the literal `Bearer ` prefix from an HTTP `Authorization` header. On the server side, `jwt()` relies on `ReactiveJwtDecoder`; if the token is expired or has an invalid signature, the request fails with an authentication error.

## 16. Testing must use RSocketRequester, not only WebTestClient

`WebTestClient` is for HTTP WebFlux and does not perform RSocket SETUP, metadata encoding, or request-stream frames. The test suite below starts the RSocket server on a **random TCP port**.

Spring Boot 3.3 provides `@LocalRSocketServerPort` in package `org.springframework.boot.test.rsocket.server`, with `spring.rsocket.server.port=0`; the client uses `RSocketRequester.Builder.connectTcp(...)`.

Required checks:
- Correct username/password at SETUP is allowed to call routes.
- Missing credentials are rejected on private routes.
- Wrong password at SETUP or per-request is rejected.
- Correct username/password per-request on an anonymous connection is accepted.
- Stream emits only the exact expected number of events; unlisted routes are denied.
- Bearer metadata is read properly by the JWT authentication pipeline; valid scope passes, missing scope fails.
- JWT cryptography/issuer/audience/expiry must be tested separately with signed tokens, without treating a Mockito decoder as real verification.

## 17. SimpleAuthRSocketTest.java — real TCP security tests

~~~java
package demo.rsocket;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;

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
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest(properties = {
    "spring.profiles.active=simple",
    "spring.rsocket.server.port=0",
    "demo.rsocket.password=lab-only-password"
})
class SimpleAuthRSocketTest {

    static final MimeType AUTH = MimeTypeUtils.parseMimeType(
        WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

    @LocalRSocketServerPort int port;

    @Autowired
    ObjectProvider<RSocketRequester.Builder> builders;

    Mono<RSocketRequester> connected(String password) {
        RSocketRequester.Builder builder = builders.getObject()
            .rsocketStrategies(s ->
                s.encoder(new SimpleAuthenticationEncoder()));
        if (password != null) {
            builder.setupMetadata(
                new UsernamePasswordMetadata("demo", password), AUTH);
        }
        return builder.connectTcp("127.0.0.1", port);
    }

    @Test
    void correctSetupCredentialsAllowEcho() {
        StepVerifier.create(connected("lab-only-password")
                .flatMap(r -> r.route("secure.echo")
                    .data("hi").retrieveMono(String.class)))
            .expectNext("echo:hi").verifyComplete();
    }

    @Test
    void missingCredentialsCannotReadPrivateRoute() {
        StepVerifier.create(connected(null)
                .flatMap(r -> r.route("secure.echo")
                    .data("hi").retrieveMono(String.class)))
            .expectError().verify();
    }

    @Test
    void wrongSetupPasswordIsRejected() {
        StepVerifier.create(connected("wrong")
                .flatMap(r -> r.route("secure.echo")
                    .data("hi").retrieveMono(String.class)))
            .expectError().verify();
    }

    @Test
    void perRequestSimpleCredentialsAreAccepted() {
        StepVerifier.create(connected(null)
                .flatMap(r -> r.route("secure.echo")
                    .metadata(new UsernamePasswordMetadata(
                        "demo", "lab-only-password"), AUTH)
                    .data("request").retrieveMono(String.class)))
            .expectNext("echo:request").verifyComplete();
    }

    @Test
    void invalidRequestCredentialIsRejected() {
        StepVerifier.create(connected(null)
                .flatMap(r -> r.route("secure.echo")
                    .metadata(new UsernamePasswordMetadata(
                        "demo", "wrong"), AUTH)
                    .data("request").retrieveMono(String.class)))
            .expectError().verify();
    }

    @Test
    void streamOnlyEmitsRequestedElements() {
        StepVerifier.create(connected("lab-only-password")
                .flatMap(r -> r.route("secure.stream")
                    .data(3).retrieveFlux(String.class).collectList()))
            .assertNext(list -> assertEquals(
                List.of("event-0", "event-1", "event-2"), list))
            .verifyComplete();
    }

    @Test
    void unknownRouteDoesNotBecomePublic() {
        StepVerifier.create(connected("lab-only-password")
                .flatMap(r -> r.route("admin.secret")
                    .data("x").retrieveMono(String.class)))
            .expectError().verify();
    }
}
~~~

**Seven tests** verify RSocket TCP, metadata encoder, and route authorization. They have no HTTP 401/403 status: the tests expect an RSocket error signal. `ObjectProvider<RSocketRequester.Builder>` obtains a fresh builder for each connection, avoiding SETUP metadata from a previous test "sticking" to the next test; the builder is mutable/prototype. A real test suite also needs lifecycle connection teardown/`dispose()` to avoid leaking resources in long CI runs.

The tests use a demo account with BCrypt; they do not prove production LDAP/IdP, JWT trust, TLS, or distributed session authorization.

## 18. JwtBearerRSocketTest.java — metadata + scope, not a replacement for crypto tests

~~~java
package demo.rsocket;

import static org.mockito.Mockito.when;

import java.time.Instant;
import io.rsocket.metadata.WellKnownMimeType;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.boot.test.rsocket.server.LocalRSocketServerPort;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.rsocket.metadata.BearerTokenMetadata;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest(properties = {
    "spring.profiles.active=jwt",
    "spring.rsocket.server.port=0"
})
class JwtBearerRSocketTest {

    static final MimeType AUTH = MimeTypeUtils.parseMimeType(
        WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

    @LocalRSocketServerPort int port;

    @Autowired
    ObjectProvider<RSocketRequester.Builder> builders;

    @MockBean
    ReactiveJwtDecoder jwtDecoder;

    Mono<String> ask(String token) {
        return builders.getObject()
            .connectTcp("127.0.0.1", port)
            .flatMap(r -> r.route("secure.echo")
                .metadata(new BearerTokenMetadata(token), AUTH)
                .data("hi").retrieveMono(String.class));
    }

    Jwt fakeJwt(String scopes) {
        Instant now = Instant.now();
        return Jwt.withTokenValue("test-value")
            .header("alg", "RS256")
            .subject("alice")
            .issuedAt(now.minusSeconds(5))
            .expiresAt(now.plusSeconds(300))
            .claim("scope", scopes)
            .claim("aud", new String[]{"messages-api"})
            .build();
    }

    @Test
    void validMockJwtWithReadScopeMayEcho() {
        when(jwtDecoder.decode("token-with-read"))
            .thenReturn(Mono.just(fakeJwt("messages.read")));
        StepVerifier.create(ask("token-with-read"))
            .expectNext("echo:hi").verifyComplete();
    }

    @Test
    void jwtWithoutScopeIsRejectedByAuthorization() {
        when(jwtDecoder.decode("limited-token"))
            .thenReturn(Mono.just(fakeJwt("profile")));
        StepVerifier.create(ask("limited-token"))
            .expectError().verify();
    }

    @Test
    void jwtDecoderErrorRejectsRequest() {
        when(jwtDecoder.decode("invalid-token"))
            .thenReturn(Mono.error(
                new BadJwtException("Invalid JWT")));
        StepVerifier.create(ask("invalid-token"))
            .expectError().verify();
    }
}
~~~

**Three tests** illustrate Spring RSocket reading Bearer metadata, passing it through the decoder, and checking scopes. `@MockBean ReactiveJwtDecoder` **does not verify real signatures/iss/exp/nbf/aud**. In a production test suite, you must have dedicated tests signing RSA with a test private key, verifying via `NimbusReactiveJwtDecoder` and a fake JWKS, and testing bad signatures, wrong issuers, wrong audiences, expired tokens, and future `nbf`.

`@MockBean` is used per Boot 3.3; in newer Boot versions the mocking API may differ. Never accept the fake token `test-value` outside mock test classes.

## 19. Build, server run, and client commands

On Java 17+ and Maven, in the directory containing `pom.xml`:

~~~bash
mvn clean test
mvn -q -DskipTests package
~~~

The test classes configure a random RSocket TCP port and do not require a real IdP for the mocked part. Tests must be run in an environment with compatible Maven/JDK; this is **instructional code**, not a compilation result verified in this conversation.

Run the `simple` profile locally:

~~~bash
export DEMO_RSOCKET_PASSWORD="lab-only-password"
export SPRING_PROFILES_ACTIVE=simple
mvn spring-boot:run
~~~

On PowerShell:

~~~powershell
$env:DEMO_RSOCKET_PASSWORD = "lab-only-password"
$env:SPRING_PROFILES_ACTIVE = "simple"
mvn spring-boot:run
~~~

Open another terminal and run the client:

~~~bash
java -cp target/classes demo.rsocket.SimpleClient
~~~

**Classpath note:** `SimpleClient` depends on Spring/RSocket libraries; `java -cp target/classes` **does not include dependency classpath entries** for a standalone client. Use the Maven exec plugin with project dependencies, for example:

~~~bash
mvn org.codehaus.mojo:exec-maven-plugin:3.3.0:java \
  -Dexec.mainClass=demo.rsocket.SimpleClient
~~~

In PowerShell you can enter it on one line:

~~~powershell
mvn org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=demo.rsocket.SimpleClient
~~~

When `localhost:7000` is running and the password matches, expected stdout:

~~~text
echo:hello
[event-0, event-1, event-2]
~~~

Do not commit real passwords/JWTs into Git, logs, process command arguments, or recordings. This is local TCP **without TLS**; switch to TLS/WSS when running over a real network.

## 20. Running the JWT profile with a real IdP

Create an appropriate OAuth2 Client to obtain an **access token** issued by an Identity Provider for audience `messages-api`. Do not take a login ID Token and arbitrarily use it as an RSocket access token.

Once you have a real IdP and valid JWKS, set the configuration:

~~~bash
export SPRING_PROFILES_ACTIVE=jwt
export RSOCKET_JWT_ISSUER="https://idp.example.com/realms/demo"
export RSOCKET_JWKS_URI="https://idp.example.com/realms/demo/protocol/openid-connect/certs"
export RSOCKET_JWT_AUDIENCE="messages-api"
mvn spring-boot:run
~~~

The client must send:

~~~java
MimeType mimeType = MimeTypeUtils.parseMimeType(
    WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

Mono<RSocketRequester> requester = RSocketRequester.builder()
    .setupMetadata(new BearerTokenMetadata(accessToken), mimeType)
    .connectTcp("127.0.0.1", 7000);
~~~

This is a **snippet**; `accessToken` must be obtained from a valid OAuth2 client/server. To use request-level identity, replace `setupMetadata(...)` with `route(...).metadata(new BearerTokenMetadata(accessToken), mimeType)`.

The default `.invalid` lab issuer cannot validate real Bearer tokens. Do not "fix" 401s by removing issuer/audience/signature validation. Ensure JWKS over HTTPS, proper algorithms, accurate NTP clocks, and monitored key rotation.

## 21. Long streams: expiry and revocation do not update automatically

Suppose a user opens a request-stream with a JWT valid for 60 seconds. The decoder verifies it when the request starts; 60 seconds later the token expires, yet **the running stream may not close automatically**, because security checked at initial authorization. This must be addressed per security SLA rather than assuming the framework performs continuous authorization.

Strategies:
1. Cap stream duration, forcing the client to re-subscribe with a fresh token after an interval.
2. Before emitting sensitive data, verify current owner/tenant and permissions in the service.
3. Listen to revocation/user-disabled events to close active streams when needed.
4. When roles/tenants change, close connections or re-authorize streams per policy.
5. For long-lived SETUP credentials, set a maximum connection age and force reconnect.
6. If a stream is CANCELed, stop upstream work and release DB/Redis/Netty resources.

Do not guarantee "when a JWT is revoked at the IdP, the RSocket stream stops immediately" when using only local JWT signature validation. Stateless JWTs do not know about instant revocation without an additional signal/introspection/state mechanism.

## 22. Backpressure and cancellation are part of security

RSocket coordinates demand via `REQUEST_N`, and the client can cancel a stream with `CANCEL`. Even for authenticated users, you still need:
- Maximum concurrent streams per user/tenant.
- Maximum payload/metadata sizes and deserialization limits.
- Rate limits, timeouts, quotas, and bounded buffers.
- Stopping the generator on cancel; do not call `subscribe()` arbitrarily to spawn ownerless background processes.
- `doFinally` or resource-aware operators for cleanup/auditing.
- Data-level tenant filters checked on every subscription.
- Never unconditionally retry Request-Channel or Fire-and-Forget operations with side effects if a response times out.

With `Flux.interval(Duration.ofMillis(100))`, add `take(max)` or a termination mechanism. For sensitive data streams, require periodic reauthentication instead of infinite streams relying on stale permissions.

## 23. Shared requester, token relay, and Reactor Context

A gateway receiving HTTP from Alice and Bob might use a single `RSocketRequester` to downstream. If the requester holds Alice's token at SETUP, Bob's requests may be treated as Alice; this is a severe isolation bug.

**Safe model:**
- Peer identity at SETUP (if used) represents the workload/gateway, never impersonating an arbitrary user.
- End-user tokens must be explicitly attached per request, with valid audience/scopes for downstream.
- Do not blindly relay inbound JWTs to every service; OAuth2 Token Exchange / On-Behalf-Of is often required.
- Keep principal/tenant in the Reactor Context of the current request, never in a mutable global `ThreadLocal`.
- When switching users, do not reuse a connection bound to a previous user without per-request auth.
- Test concurrent Alice/Bob with two mock JWTs and different tenants to detect cross-request leakage.

Do not put Bearer tokens in RSocket route strings, payloads, or loggers. `BearerTokenMetadata` travels in protocol metadata and can still be exposed by wiretap/APM if not redacted.

## 24. RSocket resume/reconnect differs from fresh authentication

RSocket can support resume depending on configuration. Resuming a protocol session **does not necessarily** create a new `SETUP` or re-execute authentication like a brand-new connection. When a token is revoked/expired or a user changes tenants:
- Evaluate maximum connection/session age.
- Consider disabling resume for high-risk subscriptions.
- Close the requester and reopen with freshly issued credentials.
- Never auto-reconnect forever with a stale password/JWT.
- Use backoff/jitter when servers restart to avoid thundering herds.
- Separate authentication retries from business action retries, especially FNF/channels with side effects.

Do not claim "resume automatically re-authenticates" without verifying the actual implementation and security chain. Only fresh SETUP and/or request metadata validation per rules determines the outcome.

## 25. TLS, WebSocket, CORS, and metadata leakage

RSocket uses TCP or WebSocket. When exposed publicly:
- Use RSocket TCP/TLS or WSS; verify server certificates.
- Restrict ingress, ports, and origins at the WebSocket handshake per threat model.
- Limit connections/frames/metadata and enforce mTLS for sensitive workloads.
- Redact username/password, JWTs, and sensitive claims in Netty wiretap, proxies, APM, tracing, and error frames.
- Do not treat browser CORS/Origin as authentication; TCP RSocket clients do not obey Same-Origin Policy.
- An HTTP WebSocket handshake may be authenticated, yet RSocket route authorization is still required if handlers use separate metadata.
- Never forward Bearer tokens to unknown hosts during redirects/proxying; use allowlisted destinations.
- Protect JWKS retrieval, issuer allowlists, and token rotation.

**HTTP CSRF does not automatically apply to RSocket TCP** like cookie POSTs, but if browsers use a WebSocket/cookie handshake, origin/cross-site WebSocket hijacking and session policies must be evaluated. Never conclude "RSocket needs no security because it goes over WebSocket" to skip route checks.

## 26. Common errors and troubleshooting table

| Symptom | Possible cause | What to do |
| --- | --- | --- |
| Server accepts route even without login | Matcher order or missing RSocket interceptor | `@EnableRSocketSecurity`, deny-all, and boot wiring |
| Simple credentials rejected | Missing encoder / wrong auth MIME / password | `SimpleAuthenticationEncoder`, `UsernamePasswordMetadata` |
| HTTP Basic header has no effect | RSocket requires authentication metadata | Send via the MIME extension |
| Valid JWT but request fails | Audience/issuer/time/algorithm or scope | Check decoder + authorities |
| Shared requester mixes Alice/Bob | SETUP token used for first user | Per-request tokens or separate connections |
| Wrong route gets an RSocket error | `anyRequest().denyAll()` | This is safe behavior |
| Stream continues after token exp | Authenticated only at start | Stream max-age, cancel/revalidation policy |
| RSocket TCP exposes credentials | Running plaintext outside localhost | TLS/WSS and redaction |
| Many streams exhaust memory | Missing quotas/backpressure | Limits, demand, cancellation |
| HTTP tests pass but RSocket fails | `WebTestClient` does not send RSocket frames | Use `RSocketRequester` integration tests |
| Mock JWT test passes but prod fails | Mock skips crypto validation | Signed JWT + trusted JWKS tests |
| Reconnect still uses revoked credentials | Client caches old token/setup | Refresh and reauthenticate |
| FNF send succeeds but data isn't saved | No application-level ack | Build a response pattern if commit confirmation is needed |
| Custom decoder accepts JWT with wrong `aud` | Forgot audience validator | Add exact audience membership check |
| Looking for 401/403 in RSocket error | RSocket has no HTTP status per frame | Inspect protocol exceptions, gateway mapping |

Debug in order: server transport + boot dependencies → security interceptor → SETUP decision → auth MIME + metadata encoder → authentication manager/decoder → scope/role matcher → handler → stream/backpressure → client lifecycle. Never lower authentication policies just to "make the demo run."

## 27. Exercises and checklist

**A — SETUP Simple:** Run the `simple` profile, send username/password via Simple metadata at SETUP, access echo/stream. Change to a wrong password and prove the request is rejected.

**B — Per-request Simple:** Open anonymous SETUP, send valid metadata on one request and no metadata on the next. Explain why the results differ.

**C — Bearer JWT:** Integrate a sandbox IdP, send a token with `aud=messages-api` and scope `messages.read`; verify the route is allowed and a token with the wrong audience is rejected.

**D — Rule precedence:** Try putting `anyRequest().permitAll()` before a private route in a test-only experiment, then fix it; describe the bypass bug.

**E — Shared connection:** Have two different principals share the same requester, each request carrying its own credentials; assert no tenant/user mix-up.

**F — Long stream:** Set a max stream duration and `take(n)`, test `CANCEL` to prove no further events are generated; add a mid-stream revocation test.

**G — FNF:** Build a route with explicit acknowledgment if the business requires commit confirmation, rather than relying solely on `send()`.

**H — TLS:** Move TCP from localhost to TLS/WSS in staging, verify certs/proxy logs, and confirm auth metadata is not logged.

**Checklist:**
- [ ] RSocket setup/routes and HTTP requests are distinct.
- [ ] `RSocketSecurity` and `PayloadSocketAcceptorInterceptor` are actually wired.
- [ ] Simple auth uses `UsernamePasswordMetadata` + `SimpleAuthenticationEncoder`.
- [ ] Bearer uses `BearerTokenMetadata` and `ReactiveJwtDecoder`.
- [ ] Valid JWT requires valid signature/iss/exp/nbf/aud/scope.
- [ ] Route matchers are in the right order, with `anyRequest` deny-all.
- [ ] Shared connections do not mix user/setup identities.
- [ ] Long streams have expiry/revocation/cancellation policies.
- [ ] RSocket TCP beyond localhost is protected with TLS/WSS.
- [ ] Separate real TCP tests, mock decoder tests, and crypto negative tests exist.
- [ ] No secrets/tokens logged; quotas and backpressure are enforced.
- [ ] RSocket errors are not assumed to be HTTP 401/403.

## 28. Self-check questions and references

1. How do RSocket SETUP authentication and per-request authentication differ?
2. Why is WebFlux `SecurityWebFilterChain` insufficient for RSocket TCP?
3. Why is Simple Authentication not HTTP Basic?
4. Which encoder does the client need for `UsernamePasswordMetadata`?
5. From which `WellKnownMimeType` must the authentication MIME type be taken?
6. What happens if `anyRequest().permitAll()` precedes a private route?
7. Does `BearerTokenMetadata` contain an HTTP `Authorization` header?
8. Can a JWT with the right issuer but wrong audience enter the service?
9. Once a stream is open, does token expiration automatically terminate the stream?
10. Why is a shared requester holding a user token at SETUP dangerous?
11. Does a mock `ReactiveJwtDecoder` verify cryptographic signatures?
12. Why shouldn't RSocket errors be asserted by HTTP status?
13. Why does connection resume not automatically mean a fresh login?
14. When must TLS/WSS and redaction be used?

**Official documentation:**
- [Spring Security — RSocket Security](https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/rsocket.html): SETUP/request authentication, Simple/JWT metadata, `authorizePayload`.
- [Spring Security — RSocketSecurity Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/rsocket/RSocketSecurity.html): `simpleAuthentication`, `jwt`, `authorizePayload`.
- [Spring Boot — RSocket](https://docs.spring.io/spring-boot/3.3/reference/messaging/rsocket.html): TCP/WebSocket, server autoconfiguration, requester.
- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): interaction models, `@MessageMapping`, metadata, streams.
- [Spring Security — SimpleAuthenticationEncoder](https://docs.spring.io/spring-security/site/docs/6.3.8/api/org/springframework/security/rsocket/metadata/SimpleAuthenticationEncoder.html): client auth encoder.
- [Spring Security — Reactive OAuth2 JWT Resource Server](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html): JWT validators.
- [Spring — RSocket Security Getting Started](https://spring.io/blog/2020/06/17/getting-started-with-rsocket-spring-security/): examples.
- [Spring — Testing RSocket Responders](https://spring.io/blog/2020/05/25/getting-started-with-rsocket-testing-spring-boot-responders): testing real TCP requests.
- [RSocket Protocol](https://rsocket.io/about/protocol/): frames, backpressure, resumability.
- [RFC 7519 — JWT](https://www.rfc-editor.org/rfc/rfc7519): `iss`, `aud`, `exp`, `nbf`.
- [RFC 8725 — JWT Security Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm/key confusion, audience.
- [OWASP — WebSocket Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html): WSS/origin/connection security when using RSocket over WebSocket.

**Conclusion:** Spring Security Reactive uses `RSocketSecurity` and authentication metadata to protect RSocket rather than relying on HTTP filters. Simple Authentication sends username/password via the right encoder; Bearer JWT requires a trusted `ReactiveJwtDecoder` plus issuer/audience/time/scope checks. Clearly define the security boundary at SETUP or per REQUEST, never use a single user's SETUP identity for shared connections, and control stream age/cancellation/revocation. Reliable test results must include **RSocket TCP metadata/route tests**, plus dedicated **JWT cryptographic tests** before production deployment.