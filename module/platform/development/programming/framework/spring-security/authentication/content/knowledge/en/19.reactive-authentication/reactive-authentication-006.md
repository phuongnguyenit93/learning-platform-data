# AuthenticationWebFilter and ServerAuthenticationConverter — Reactive Authentication in Spring Security

> **Module:** Spring Security - authentication. **Branch:** Reactive authentication. This lesson explains how `AuthenticationWebFilter` coordinates with `ServerAuthenticationConverter`, `ReactiveAuthenticationManager`, the Reactor Context, and authorization rules in **Spring WebFlux**. Includes a standalone runnable example using **Java 17, Spring Boot 3.3.5, Spring Security 6.x, and Maven**, plus `WebTestClient` tests. The sample authentication mechanism is an API key in a header to clearly expose responsibility boundaries; production should prefer standard OAuth2/JWT when appropriate.

## 1. How Is Spring Security Reactive Different from Spring MVC?

Spring MVC runs on the Servlet stack; Spring WebFlux provides an asynchronous processing model using Reactor `Mono`/`Flux`. If you are only used to `OncePerRequestFilter`, `HttpServletRequest`, and ThreadLocal-based `SecurityContextHolder`, it is easy to misconfigure when moving to reactive.

| Servlet component | Corresponding WebFlux component |
| --- | --- |
| `jakarta.servlet.Filter` | `org.springframework.web.server.WebFilter` |
| `HttpServletRequest` and `HttpServletResponse` | `ServerWebExchange`, reactive request/response |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `HttpSecurity` | `ServerHttpSecurity` |
| `AuthenticationManager` returning `Authentication` directly | `ReactiveAuthenticationManager` returning `Mono<Authentication>` |
| `AuthenticationFilter` or other auth filters | `AuthenticationWebFilter` |
| `AuthenticationConverter` with servlet request | `ServerAuthenticationConverter` with `ServerWebExchange` |
| `SecurityContextHolder` typically ThreadLocal-based | `ReactiveSecurityContextHolder` based on Reactor Context |
| `HttpSession` | `WebSession` when session-based security is needed |
| `MockMvc` in Servlet | `WebTestClient` for Spring WebFlux |

**Important:** WebFlux does not automatically turn all Java I/O into non-blocking I/O. A converter calling `.block()` or a manager running blocking JDBC on the Netty event loop can severely degrade throughput. The reactive stack requires both the APIs and key dependencies to be used properly.

**Lesson scenario:** An API exposes `GET /api/data` for clients with read permission and `GET /api/admin` for admin clients. Clients send an `X-API-Key` header; the server must verify the key before assigning a principal and roles. A client-sent `X-Role: ROLE_ADMIN` header must **not** be treated as an authority.

## 2. Exact Role of AuthenticationWebFilter

`AuthenticationWebFilter` lives in `org.springframework.security.web.server.authentication` and implements `WebFilter`. It orchestrates **a single authentication attempt** through these steps:

```text
HTTP request -> SecurityWebFilterChain
    |
    v
AuthenticationWebFilter
    |
    +-- ServerWebExchangeMatcher:
    |      no match? -> skip authentication, chain continues
    |      match?    -> call converter
    |
    +-- ServerAuthenticationConverter.convert(exchange)
    |      Mono.empty() -> no credentials, chain continues
    |      Mono.error(AuthenticationException) -> authentication failure
    |      Mono<Authentication> -> candidate to verify
    |
    +-- ReactiveAuthenticationManager.authenticate(candidate)
    |      Verified Mono<Authentication> -> success
    |      Mono.error(AuthenticationException) -> failure
    |      Mono.empty() -> manager did not supply a result
    |
    +-- Success:
    |      put trusted Authentication into Reactor SecurityContext
    |      persist context with ServerSecurityContextRepository if configured
    |      call ServerAuthenticationSuccessHandler
    |
    +-- Failure:
           call ServerAuthenticationFailureHandler
           return 401, challenge, redirect... per configuration
    |
    v
AuthorizationWebFilter / authorizeExchange
    |
    +-- no valid credentials -> handled by entry point
    +-- authenticated but lacks authority -> 403
    +-- sufficient authority -> controller/handler
```

The filter does not prove that a key/password is valid on its own, and the converter must never grant roles itself. **The filter orchestrates, the converter extracts, the manager verifies, and authorization decides access.** Those are four boundaries to keep independent.

### 2.1. Key APIs

```java
// Illustrative signatures; not a standalone compilable Java file.
new AuthenticationWebFilter(ReactiveAuthenticationManager manager);

new AuthenticationWebFilter(
    ReactiveAuthenticationManagerResolver<ServerWebExchange> resolver);

filter.setRequiresAuthenticationMatcher(matcher);
filter.setServerAuthenticationConverter(converter);
filter.setSecurityContextRepository(repository);
filter.setAuthenticationSuccessHandler(successHandler);
filter.setAuthenticationFailureHandler(failureHandler);
```

| API | When to use |
| --- | --- |
| `setRequiresAuthenticationMatcher` | Restrict which paths/requests the filter attempts to authenticate |
| `setServerAuthenticationConverter` | How to read the request and build the candidate `Authentication` |
| Constructor with `ReactiveAuthenticationManager` | Use a single fixed manager for the authentication mechanism |
| Constructor with `ReactiveAuthenticationManagerResolver<ServerWebExchange>` | Select a manager by context with a clear trust boundary (allowlisted tenant/issuer) |
| `setSecurityContextRepository` | Persist security context after success; filter defaults to `NoOpServerSecurityContextRepository` |
| `setAuthenticationSuccessHandler` | Respond or continue the chain after successful authentication |
| `setAuthenticationFailureHandler` | Translate authentication exceptions into an HTTP response |

The older `setAuthenticationConverter(Function<ServerWebExchange, Mono<Authentication>>)` API is deprecated; in Spring Security 6 call **`setServerAuthenticationConverter`**.

By default, `ServerHttpBasicAuthenticationConverter` is used if no custom converter is set. If your app uses standard HTTP Basic, form login, or an OAuth2 resource server, **prefer the built-in DSL** rather than adding a duplicate filter manually.

### 2.2. Matchers Do Not Replace Authorization

If a filter only matches `/api/**`, it does not check API keys outside that path. That does not automatically make URLs outside `/api/**` private. You must configure `authorizeExchange` independently with rules:
- Public routes get `permitAll()`.
- Routes requiring roles use `hasRole(...)`/`hasAuthority(...)`.
- Remaining routes get `denyAll()` unless public access is intended.

A serious mistake is enabling an authentication filter while leaving `anyExchange().permitAll()`, assuming endpoints are now protected.

## 3. ServerAuthenticationConverter: Turning Requests into Evidence, Without Verifying

`ServerAuthenticationConverter` is a functional interface:

```java
// Illustrative API contract.
Mono<Authentication> convert(ServerWebExchange exchange);
```

A converter can inspect headers, form bodies, or other parts of `ServerWebExchange`. It should stay small, non-blocking, and easy to test:

1. Pick the exact credential location—for instance, read only the `X-API-Key` header.
2. Check **syntax**: whether the header exists, and whether empty/length/duplicate values are acceptable.
3. If credentials are missing, return `Mono.empty()`.
4. If credentials are present yet syntactically invalid, return `Mono.error(new BadCredentialsException(...))`.
5. If syntactically valid, build an **unauthenticated** `Authentication` carrying the credential for the manager to verify.

```java
// Illustrative snippet, requires imports.
ServerAuthenticationConverter converter = exchange -> {
    String key = exchange.getRequest().getHeaders().getFirst("X-API-Key");
    if (key == null) {
        return Mono.empty();
    }
    if (key.isBlank()) {
        return Mono.error(new BadCredentialsException("Invalid API key"));
    }
    return Mono.just(
        UsernamePasswordAuthenticationToken.unauthenticated("api-key", key)
    );
};
```

This borrows `UsernamePasswordAuthenticationToken` to illustrate a candidate. In production you can define a dedicated `ApiKeyAuthenticationToken` for that credential type. Token naming does not alter the principle: **trusted principals and authorities appear only after the provider/manager verifies**.

### 3.1. Exact Meaning of Each Signal

| Signal | Meaning | Processing path |
| --- | --- | --- |
| `Mono.empty()` | Converter found no credentials | Filter skips authentication; authorization decides whether 401 is needed |
| `Mono.just(candidate)` | Syntactically valid evidence exists | Hands candidate to manager |
| `Mono.error(BadCredentialsException)` | Encountered unacceptable credentials | Failure handler processes it; in the demo, returns 401 |
| `Mono.just(null)` | **Violates Reactor contract** | Reactor forbids emitting null |
| Candidate with `ROLE_ADMIN` from `X-Role` | **Violates trust boundary** | Risks privilege escalation |

Do not convert `Mono.empty()` into `anonymous authenticated`; missing credentials simply mean **no authentication attempt**. A `permitAll` resource can return 200, while a resource requiring `authenticated()` will reject it.

### 3.2. Converters Reading Request Bodies Need Extra Care

Reactive request bodies are usually single-consumption streams. Reading the body in a filter and letting a controller read it again without proper caching/coordination can fail or drop data. When parsing JSON/form logins:
- Validate `Content-Type`, body size, charset, and schema.
- Use WebFlux reactive APIs; never call `.block()` on the event loop.
- Avoid logging raw passwords/tokens.
- Use Spring Security's built-in converters (such as `ServerFormLoginAuthenticationConverter`) when appropriate.
- Preserve CSRF protection when browsers attach credentials automatically.

This article's header-only converter does not need to touch the body.

## 4. ReactiveAuthenticationManager Is Where Credentials Are Verified

`ReactiveAuthenticationManager` exposes:

```java
Mono<Authentication> authenticate(Authentication authentication);
```

This is the component permitted to check evidence against a trusted server-side source (secret manager, reactive user store, configured issuer/decoder, IdP, etc.). In the demo:

```text
Input from converter:
  UsernamePasswordAuthenticationToken.unauthenticated(
      "api-key", "demo-reader-key-123")

ReactiveAuthenticationManager:
  look up server-provisioned key
  verify key
  if valid: build principal/role per server registry
  if invalid: Mono.error(new BadCredentialsException(...))

Success output:
  UsernamePasswordAuthenticationToken.authenticated(
      "reader-service", null, [ROLE_READER])
```

The manager must **never trust** `authenticated`, `role`, `scope`, or `tenant` fields supplied by the client. Never write code that takes JSON such as:

```json
{
  "apiKey": "wrong",
  "authenticated": true,
  "authorities": ["ROLE_ADMIN"]
}
```

and uses that JSON to construct an authenticated `Authentication`. Doing so turns untrusted input into server privileges.

### 4.1. Manager Mono.empty Differs from Bad Credentials

`Mono.empty()` from a manager fits cases where **the manager does not support that token type** and explicit delegation exists. If the token is a supported type yet the key is wrong, return an `AuthenticationException` (such as `BadCredentialsException`) rather than skipping it as if no request existed. That lets failure handlers respond properly and keeps observability clear.

### 4.2. Truly Reactive Means Never Blocking

In production, if you query a database over the network to verify keys, prefer reactive repositories/drivers like R2DBC or reactive Redis; use `flatMap` and sensible timeouts. Never call blocking JDBC directly in a converter or manager on the Netty event loop. If forced to bridge a blocking library, use an appropriate scheduler, concurrency limits, timeouts, and load monitoring; never treat `Mono.just(blockingCall())` as non-blocking.

## 5. How Does a Successful Authentication Live in the Reactor Context?

In the Servlet stack, code commonly reads `SecurityContextHolder.getContext()` from thread-local storage. In WebFlux, execution can hop threads across schedulers or callbacks. `ReactiveSecurityContextHolder` uses Reactor's `Context` to associate `SecurityContext` with the reactive subscription.

After the filter authenticates successfully, Spring Security populates the context for downstream components. Controllers can accept `Mono<Principal>`:

```java
// Snippet for use inside a reactive service when a trusted username is needed.
Mono<String> currentName =
    ReactiveSecurityContextHolder.getContext()
        .map(security -> security.getAuthentication().getName());
```

Never read a username from `X-User` or client JSON and call it the authenticated principal. Likewise, do not create your own `ThreadLocal` named `currentUser` in a reactive pipeline without proper context propagation design.

### 5.1. Stateless vs. Session-Based

- **`NoOpServerSecurityContextRepository`**: does not save the security context into `WebSession`. Subsequent requests without an API key must authenticate again; fits stateless header API keys/Bearer tokens in the demo.
- **`WebSessionServerSecurityContextRepository`**: can save the context into `WebSession` for interactive logins; requires proper session, CSRF, session fixation, logout, and cookie policies.
- `ServerHttpSecurity.securityContextRepository(...)` governs how the context is loaded into the reactive chain; `AuthenticationWebFilter.setSecurityContextRepository(...)` governs where the filter **saves** the context after successful auth. Both should agree.

**Avoid package confusion:** WebFlux's `ServerSecurityContextRepository` differs from Servlet's `SecurityContextRepository`. Injecting a Servlet repository into a reactive filter is a type mismatch.

## 6. Complete Spring Boot WebFlux Project

We will build a custom API key flow so the converter and manager are easy to observe. The system exposes:
- `GET /health`: public, returns `ok`.
- `GET /api/data`: requires `ROLE_READER` or `ROLE_ADMIN`.
- `GET /api/admin`: requires `ROLE_ADMIN`.

The demo puts two keys in **local-only** config, not production secrets. Do not add `spring-boot-starter-web` because the goal is WebFlux (when both MVC and WebFlux are on the classpath, Spring Boot normally picks MVC unless overridden).

### 6.1. File Structure

```text
reactive-filter-demo/
├── pom.xml
├── src/main/resources/application.properties
├── src/main/java/com/example/reactiveauth/ReactiveAuthApplication.java
└── src/test/java/com/example/reactiveauth/ReactiveAuthApplicationTests.java
```

### 6.2. Maven: `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>reactive-filter-demo</artifactId>
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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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
```

### 6.3. Local Config `application.properties`

```properties
# For running this exercise on a local machine only. Do not use in production.
demo.auth.reader-key=demo-reader-key-123
demo.auth.admin-key=demo-admin-key-456
```

These values are **predictable illustrative keys**. In real systems, keys must be generated with high cryptographic entropy, stored/checked via key IDs and a secret manager or proper hashing/HMAC, and support rotation and revocation. Never commit or log real keys.

### 6.4. Java: `ReactiveAuthApplication.java`

```java
package com.example.reactiveauth;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.Principal;
import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.AuthenticationWebFilter;
import org.springframework.security.web.server.authentication.HttpStatusServerEntryPoint;
import org.springframework.security.web.server.authentication.ServerAuthenticationConverter;
import org.springframework.security.web.server.authentication.ServerAuthenticationEntryPointFailureHandler;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveAuthApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveAuthApplication.class, args);
    }

    @Bean
    ServerAuthenticationConverter apiKeyConverter() {
        return exchange -> {
            List<String> headers =
                    exchange.getRequest().getHeaders().get("X-API-Key");

            // No header -> do not attempt authentication.
            if (headers == null) {
                return Mono.empty();
            }

            // Header present but malformed -> authentication failure.
            if (headers.size() != 1 || headers.get(0).isBlank()
                    || headers.get(0).length() > 128) {
                return Mono.error(
                        new BadCredentialsException("Invalid API key"));
            }

            // Unauthenticated candidate Authentication.
            return Mono.just(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "api-key", headers.get(0))
            );
        };
    }

    @Bean
    ReactiveAuthenticationManager apiKeyAuthenticationManager(
            @Value("${demo.auth.reader-key}") String readerKey,
            @Value("${demo.auth.admin-key}") String adminKey) {

        return authentication -> {
            if (!(authentication instanceof UsernamePasswordAuthenticationToken)) {
                return Mono.empty();
            }

            Object credentials = authentication.getCredentials();
            if (!(credentials instanceof String supplied)) {
                return Mono.error(
                        new BadCredentialsException("Invalid API key"));
            }

            // Authorities are determined by server-side keys, never from X-Role.
            if (sameSecret(supplied, readerKey)) {
                return Mono.just(
                    UsernamePasswordAuthenticationToken.authenticated(
                        "reader-service",
                        null,
                        List.of(new SimpleGrantedAuthority("ROLE_READER"))
                    )
                );
            }

            if (sameSecret(supplied, adminKey)) {
                return Mono.just(
                    UsernamePasswordAuthenticationToken.authenticated(
                        "admin-service",
                        null,
                        List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
                    )
                );
            }

            return Mono.error(
                    new BadCredentialsException("Invalid API key"));
        };
    }

    // Constant-time byte comparison; production needs stricter hash/key management.
    private static boolean sameSecret(String supplied, String expected) {
        return MessageDigest.isEqual(
                supplied.getBytes(StandardCharsets.UTF_8),
                expected.getBytes(StandardCharsets.UTF_8)
        );
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager apiKeyAuthenticationManager,
            ServerAuthenticationConverter apiKeyConverter) {

        AuthenticationWebFilter apiKeyFilter =
                new AuthenticationWebFilter(apiKeyAuthenticationManager);

        apiKeyFilter.setRequiresAuthenticationMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**")
        );
        apiKeyFilter.setServerAuthenticationConverter(apiKeyConverter);
        apiKeyFilter.setSecurityContextRepository(
                NoOpServerSecurityContextRepository.getInstance()
        );
        apiKeyFilter.setAuthenticationFailureHandler(
            new ServerAuthenticationEntryPointFailureHandler(
                new HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED)
            )
        );

        return http
            // Do not load security context from WebSession.
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance()
            )
            // Only in stateless API key demo; no browser cookies used.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .logout(ServerHttpSecurity.LogoutSpec::disable)
            .exceptionHandling(ex -> ex.authenticationEntryPoint(
                new HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED)
            ))
            .authorizeExchange(ex -> ex
                .pathMatchers("/health").permitAll()
                .pathMatchers("/api/admin").hasRole("ADMIN")
                .pathMatchers("/api/data").hasAnyRole("READER", "ADMIN")
                .anyExchange().denyAll()
            )
            .addFilterAt(apiKeyFilter, SecurityWebFiltersOrder.AUTHENTICATION)
            .build();
    }

    public record Identity(String username, List<String> authorities) {}

    @RestController
    static class ApiController {
        @GetMapping("/health")
        Mono<String> health() {
            return Mono.just("ok");
        }

        @GetMapping("/api/data")
        Mono<Identity> data(Mono<Principal> principal) {
            return principal.map(p -> {
                Authentication auth = (Authentication) p;
                List<String> roles = auth.getAuthorities().stream()
                        .map(GrantedAuthority::getAuthority)
                        .sorted()
                        .toList();
                return new Identity(auth.getName(), roles);
            });
        }

        @GetMapping("/api/admin")
        Mono<String> admin() {
            return Mono.just("admin-only");
        }
    }
}
```

### 6.5. Explaining Every Decision in the Example

1. **Converter only extracts credentials.** One `X-API-Key` header is syntax-checked; duplicate, blank, or oversized headers error. The candidate is built via `UsernamePasswordAuthenticationToken.unauthenticated` with no authorities.
2. **Manager determines identity.** It compares the key against server-provisioned values and returns `UsernamePasswordAuthenticationToken.authenticated` with official principal/authorities. Users cannot pick roles via headers.
3. **Never blocking the event loop.** Demo key comparison is a tiny in-memory check. When replaced with a DB/IdP, use a reactive driver/client; never call `block()` just to “keep old syntax”.
4. **Filter matcher:** `/api/**` checks API keys. `/health` avoids forcing the converter to inspect unrelated headers.
5. **Clear 401 response:** the filter's failure handler returns status 401 for bad credentials; the same entry point status applies when authorization requires an authenticated principal and the request lacks a key.
6. **Separating authn and authz:** `READER` is insufficient for the admin route → 403; `ADMIN` suffices for the admin route → 200.
7. **Consistent statelessness:** `NoOpServerSecurityContextRepository` is configured on both the filter and `ServerHttpSecurity`; a new request without a key cannot reuse identity.
8. **Reactive principal:** the controller receives `Mono<Principal>` from the exchange after the security filter; on this route the principal is the `Authentication` created by the manager. Never read username from a query parameter.
9. **Narrowly scoped CSRF disablement:** this is a GET-only demo with manually attached header keys, without session cookies or browser-attached credentials. If adding browser login or cookie-backed POSTs, re-evaluate CSRF.
10. **No Servlet SecurityFilterChain.** The code declares only `SecurityWebFilterChain`, `ServerHttpSecurity`, and `AuthenticationWebFilter`, without adding a `OncePerRequestFilter`.

## 7. Running and Verifying Yourself with curl

From the project directory:

```bash
mvn spring-boot:run
```

Try these requests:

```bash
# Public endpoint: 200, body ok
curl -i http://localhost:8080/health

# Missing key: 401
curl -i http://localhost:8080/api/data

# Wrong key: 401
curl -i -H 'X-API-Key: invalid' \
  http://localhost:8080/api/data

# Reader key: 200, ROLE_READER from server
curl -i -H 'X-API-Key: demo-reader-key-123' \
  http://localhost:8080/api/data

# Cannot escalate privileges via client header: 403
curl -i -H 'X-API-Key: demo-reader-key-123' \
  -H 'X-Role: ROLE_ADMIN' \
  -H 'X-Authenticated: true' \
  http://localhost:8080/api/admin

# Admin key: 200
curl -i -H 'X-API-Key: demo-admin-key-456' \
  http://localhost:8080/api/admin

# Prove statelessness: after 200, a new request without header still gets 401
curl -i -H 'X-API-Key: demo-reader-key-123' \
  http://localhost:8080/api/data
curl -i http://localhost:8080/api/data
```

Illustrative JSON response on `/api/data`:

```json
{"username":"reader-service","authorities":["ROLE_READER"]}
```

Body of `/api/admin` with the admin key:

```text
admin-only
```

| Request | Expected status | Reason |
| --- | --- | --- |
| `/health` without key | 200 | Public |
| `/api/data` without key | 401 | Converter `Mono.empty()`, authorization lacks auth |
| `/api/data` invalid key | 401 | Manager emits `BadCredentialsException` |
| `/api/data` reader key | 200 | Manager grants `ROLE_READER` |
| `/api/admin` reader key + `X-Role: ROLE_ADMIN` | 403 | Client role not trusted |
| `/api/admin` admin key | 200 | Manager grants `ROLE_ADMIN` |
| Subsequent request without key | 401 | No session to restore identity |

The table describes business status codes and bodies. Extra HTTP headers depend on the server/framework; avoid hardcoding entire responses unnecessarily. For real credentials, **never put API keys in query strings**, logs, or public docs.

## 8. Testing with WebTestClient Without Bypassing Filters

Create `src/test/java/com/example/reactiveauth/ReactiveAuthApplicationTests.java`:

```java
package com.example.reactiveauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveAuthApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void healthWorksWithoutKey() {
        client.get().uri("/health")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("ok");
    }

    @Test
    void missingAndWrongKeyAreRejected() {
        client.get().uri("/api/data")
                .exchange()
                .expectStatus().isUnauthorized();

        client.get().uri("/api/data")
                .header("X-API-Key", "invalid")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void readerKeyIsAuthenticatedWithServerSideAuthority() {
        client.get().uri("/api/data")
                .header("X-API-Key", "demo-reader-key-123")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.username").isEqualTo("reader-service")
                .jsonPath("$.authorities[0]").isEqualTo("ROLE_READER");
    }

    @Test
    void clientCannotForgedAdminRole() {
        client.get().uri("/api/admin")
                .header("X-API-Key", "demo-reader-key-123")
                .header("X-Role", "ROLE_ADMIN")
                .header("X-Authenticated", "true")
                .exchange()
                .expectStatus().isForbidden();

        client.get().uri("/api/admin")
                .header("X-API-Key", "demo-admin-key-456")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin-only");
    }

    @Test
    void secondRequestNeedsOwnKey() {
        client.get().uri("/api/data")
                .header("X-API-Key", "demo-reader-key-123")
                .exchange()
                .expectStatus().isOk();

        client.get().uri("/api/data")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void malformedAndRepeatedKeyHeadersAreRejected() {
        client.get().uri("/api/data")
                .header("X-API-Key", " ")
                .exchange()
                .expectStatus().isUnauthorized();

        client.get().uri("/api/data")
                .header("X-API-Key",
                        "demo-reader-key-123", "demo-admin-key-456")
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
```

Run:

```bash
mvn test
```

**Why are these tests valuable?** They send real headers through `SecurityWebFilterChain` without pre-injecting an authenticated principal. Thus they catch bugs in matchers, converters, managers, context, and authorization. If you only use `mockUser()`, authority tests may pass even when the converter/manager is broken. `mockUser()` remains useful when you **intentionally** want to test authorization rules in isolation from authentication.

`@SpringBootTest` + `@AutoConfigureWebTestClient` tests at the WebFlux application tier, though it does not replace E2E tests covering TLS, reverse proxies, secret stores, rate limits, and multi-node deployment. The test code is provided for learners to run; **no Maven run is claimed here**.

## 9. Converter and Authentication Mechanism Variants

### 9.1. HTTP Basic

Spring Security provides `ServerHttpBasicAuthenticationConverter` to parse `Authorization: Basic ...`. Usually prefer `http.httpBasic(...)` over writing a custom Base64 converter. Base64 does not encrypt passwords; HTTPS and server-side password hashing remain mandatory.

### 9.2. Form Login

WebFlux provides `ServerFormLoginAuthenticationConverter` for form payloads. With browser logins, successful authentication can be saved into `WebSession`. That requires compatible CSRF protection, session fixation defense, logout, and cookie policies; do not blindly force a NoOp session repository.

### 9.3. JWT Bearer

For JWT-authenticated APIs, `http.oauth2ResourceServer(...jwt...)` with `ReactiveJwtDecoder` and Spring Security's provided converters/managers is the preferred path. Never Base64-decode the payload yourself and trust `iss`, `scope`, or `role` fields before verifying the signature, `aud`, expiration, issuer, and other constraints.

### 9.4. Multi-Tenant Manager Resolver

`AuthenticationWebFilter` has a constructor taking `ReactiveAuthenticationManagerResolver<ServerWebExchange>` to pick a manager per request. A tenant/issuer hint may be influenced by the client; the server must normalize it, look up a trusted registry/allowlist, select a provisioned manager/decoder, and **verify credentials with that manager**.

Never accept arbitrary JDBC URLs, LDAP hosts, or JWK URLs from the client to instantiate a manager. If a tenant does not exist, fail closed; never fall back to a global manager with broad authority.

### 9.5. Custom API Key Token

Replacing `UsernamePasswordAuthenticationToken` with a custom token is cleaner in larger systems. Even then, the token created by the converter must still be **unauthenticated**; factory methods/constructors marking authenticated should be called only after server-side verification. Avoid token classes with public setters that let `ROLE_ADMIN` be populated from request JSON.

## 10. Real-World Bugs and Diagnostics

| Symptom / bug | Possible cause | How to check / fix |
| --- | --- | --- |
| WebFlux app uses `OncePerRequestFilter` | Confusing Servlet with reactive | Use `AuthenticationWebFilter`, `ServerWebExchange` |
| Authn filter runs yet route stays public | Missing proper `authorizeExchange` rule | Test protected endpoint without key must return 401 |
| Converter always returns `Mono.empty()` | Reading wrong header/path or matcher mismatch | Inspect request headers/matchers without logging secrets |
| Wrong key yields 200 | Manager builds authenticated token with flawed logic | Audit server-side verification; never trust client |
| Valid key yields 403 | Manager authorities fail authorization rule | Check `ROLE_READER` vs `ROLE_ADMIN` |
| Cannot read principal in reactive service | Using ThreadLocal instead of Reactor Context | `ReactiveSecurityContextHolder` / reactive principal |
| Request with 2 API keys still succeeds | Converter picks first header without duplicate check | Reject malformed/duplicate headers |
| Throughput drops during login calls | Blocking DB / `block()` on event loop | Reactive driver, timeouts, bounded resources |
| Next request auto-authenticated without key | Unintended session repository config | Align NoOp on both filter and chain |
| Wrong key returns 500 | Authentication failure not mapped | `ServerAuthenticationFailureHandler` with proper entry point |
| Missing key returns 403 instead of 401 | Different rules / entry point / anonymous handling | Configure and test exception handling |
| Disabling CSRF for all routes | Browser cookies still auto-send | Evaluate credential transport and protect state-changing actions |

**Distinguishing status codes:** 401 typically indicates missing or invalid credentials; 403 means authenticated yet lacking authority. Exact responses depend on the configured entry point, failure handler, and access-denied handler. The demo explicitly configures 401 for both missing and invalid authentication.

### 10.1. Do Not Conflate Authentication with Authorization

Both `/api/data` and `/api/admin` use the same API key filter. The manager verifying the key only answers “who is this?”; the authorization step answers “what are they allowed to do?”. The `X-Role` header is client data and never alters roles granted by the manager.

### 10.2. Body-Reading Bugs When Adding JSON Login

WebFlux request bodies can be consumed once. A custom converter receiving `ServerWebExchange` that reads the body and continues the chain must handle body caching and validation properly; do not treat it like `HttpServletRequest.getInputStream()` as infinitely re-readable. Cap payload size, parse reactively, and avoid `block()`.

### 10.3. Do Not Use Request-Scoped ThreadLocal

Switching schedulers or using async callbacks can change threads. When auditing or authorization depends on the current user, read from `ReactiveSecurityContextHolder` or pass the verified principal cleanly through the reactive pipeline—never via custom static/ThreadLocal variables.

## 11. Production Hardening Checklist

1. **Secrets:** high-entropy random API keys, key IDs, secret manager, hashing/HMAC, scopes, expiry, and rotation. Never use literal demo keys outside local environments.
2. **Transport:** HTTPS/TLS, never send credentials in URLs/queries; never log raw authorization headers or body credentials.
3. **Authorization:** verify authorities from trusted sources; default to least privilege; enforce tenant/object ownership at the service/data layer.
4. **Reactive I/O:** reactive DB/clients for auth, timeouts/circuit breakers/rate limits; never unconditionally turn IdP outages into user wrong-password errors.
5. **Observability:** log only key IDs and outcomes after redaction; never store raw keys in traces, exceptions, or metric labels.
6. **Consistency:** when multiple nodes share a registry, keep config/rotation/revocation synchronized; fail closed when verification is impossible.
7. **CSRF:** disable only on analyzed stateless header-token routes. If browsers auto-send cookies, enforce proper CSRF policies.
8. **Tests:** missing key, wrong key, malformed header, forged role, valid key lacking role, stateless context, and revoked key.
9. **Simplicity:** pick standard Spring Security APIs when they fit; write custom filters only with clear justification.
10. **Boundaries:** token expiration/revocation and credential lifecycles are distinct mechanisms—they do not happen automatically just because a reactive request completes.

## 12. Self-Check Questions

1. At which step does `AuthenticationWebFilter` differ from `ServerAuthenticationConverter`?
2. Why should a converter return `UsernamePasswordAuthenticationToken.unauthenticated(...)`?
3. How does `Mono.empty()` from a converter differ from `Mono.error(BadCredentialsException)`?
4. In the demo, who grants `ROLE_READER` and `ROLE_ADMIN`?
5. Can `setRequiresAuthenticationMatcher` replace `authorizeExchange`?
6. Why can an HTTP request without a key still succeed on `/health`?
7. Why does a valid reader key still get 403 on `/api/admin`?
8. How does `ReactiveAuthenticationManager` differ in contract from Servlet `AuthenticationManager`?
9. Why is ThreadLocal `SecurityContextHolder` not the default choice for WebFlux?
10. Why must `NoOpServerSecurityContextRepository` be set on both the filter and the chain?
11. When should you use `ReactiveAuthenticationManagerResolver`, and why is a trusted registry needed?
12. When is `mockUser()` helpful, and when can it hide converter bugs?
13. Why should you never parse a JWT payload and assign roles directly?
14. Why is disabling CSRF not an automatic consequence of using WebFlux?
15. What happens when a manager calls blocking JDBC on the Netty event loop?

**Core answers:** (1) the filter orchestrates, the converter extracts credentials; (2) client credentials are untrusted yet; (3) absence of evidence vs. attempting invalid evidence; (4) the server-side manager; (5) no, authn differs from authz; (6) permitAll; (7) insufficient authority; (8) `Mono<Authentication>`; (9) Reactor execution can switch threads; (10) consistent statelessness; (11) pick an allowlisted manager and verify credentials; (12) good for isolated authorization tests, does not prove converter behavior; (13) requires signature/issuer/audience validation; (14) depends on browser credential transport; (15) blocks the event loop and reduces throughput.

## 13. Official Documentation

- Spring Security 6.5 — AuthenticationWebFilter API: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html
- Spring Security 6.5 — ServerAuthenticationConverter API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationConverter.html
- Spring Security 6.5 — ReactiveAuthenticationManager API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html
- Spring Security 6.5 — ReactiveAuthentication: https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/index.html
- Spring Security 6.5 — WebFlux Security: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security 6.5 — Reactive authorization: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html
- Spring Security 6.5 — WebTestClient Security Setup: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html
- Spring Security 6.5 — Reactive Testing Authentication: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html
- Spring Security 6.5 — CSRF WebFlux: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
