# Designing a Custom Authentication Mechanism with AuthenticationWebFilter in Spring Security WebFlux

## Objectives

This lesson belongs to **Advanced Authentication** in the **Spring Security - reactive** module. In a WebFlux application, when you need to support a credential type not already provided by HTTP Basic, OAuth2, OIDC, or JWT Resource Server, you can integrate into the **Spring Security reactive chain** using `AuthenticationWebFilter` instead of writing a global filter that manually sets a "logged in" variable.

After this lesson, you will be able to:

1. Explain the responsibilities of `AuthenticationWebFilter`, `ServerAuthenticationConverter`, `ReactiveAuthenticationManager`, `Authentication`, `ServerSecurityContextRepository`, success/failure handlers, and `AuthorizationWebFilter`.
2. Distinguish between `Mono.empty()`, `Mono.just(unauthenticatedToken)`, and `Mono.error(AuthenticationException)` in the converter and manager.
3. Construct an unverified `Authentication` from a request header; only a trusted manager creates an authenticated token with a principal and `GrantedAuthority`.
4. Use `setRequiresAuthenticationMatcher`, `setServerAuthenticationConverter`, `setAuthenticationSuccessHandler`, `setAuthenticationFailureHandler`, `setSecurityContextRepository`, and `addFilterAt` with accurate WebFlux semantics.
5. Understand when to use `NoOpServerSecurityContextRepository` (stateless per request) or `WebSessionServerSecurityContextRepository` (session-based login).
6. Write a **Java 17+, Spring Boot 3.3.13, WebFlux, Spring Security 6.3.x** application demonstrating `Authorization: DemoKey ...`.
7. Verify the `SCOPE_orders:read` authority, client identity, tenant, and order ownership; avoid confusing AuthN with AuthZ.
8. Use `ReactiveSecurityContextHolder` in services instead of Servlet `SecurityContextHolder`.
9. Test with `WebTestClient` and `StepVerifier`: public, missing key, malformed key, wrong key, authenticated, insufficient authority, tenant/owner, stateless.
10. Deploy safely to production with HTTPS, secret entropy, a hashed key store, rotation, expiry, revocation, rate limiting, CORS/CSRF, multi-chain, and redacted logs.

**Security scope:** `DemoKey` here is a **simulated protocol for lab purposes**, not a recommendation to invent a custom production auth scheme. If the use case is already met by proven OAuth2 client credentials, mTLS, JWT/opaque token Resource Server, or gateway identity, prefer those. `AuthenticationWebFilter` is a technical integration point; it does not make a weak credential format secure.

## 1. Authentication and Authorization Are Two Separate Stages

**Authentication** answers: who is calling? Does the credential presented by the caller match a key/identity record, remain unrevoked and unexpired, and is it permitted in this context?

**Authorization** answers: can the authenticated identity read or modify a **specific resource**?

A valid API key for `partner-a` in `tenant-a` does not mean that partner can read all orders. Separate these checks:

- Credential validation: the API key is valid, active, and not revoked, and the server resolves the principal `partner-a`.
- Scope check: the `Authentication` contains `SCOPE_orders:read`.
- Tenant/owner check: record `A-100` must belong to `tenant-a/partner-a`.

HTTP 200 can be returned when all three pass; return 401 if the credential is missing/invalid, 403 if authenticated but lacking authority, and optionally 404 if the order does not exist **or does not belong to the caller**, depending on your response policy.

**In particular:** `authentication.isAuthenticated()` is meaningful only after the token has been created by a verified manager; do not read a Boolean value from a request header. An authenticated `Authentication` also does **not automatically** grant access to every route or tenant.

## 2. Reactive AuthenticationWebFilter Architecture

```text
Client request
    |
    v
WebFilterChainProxy -> SecurityWebFilterChain
    |
    v
AuthenticationWebFilter
    |
    +-- requiresAuthenticationMatcher(exchange)?
    |      no => continue chain
    |      yes
    |
    +-- ServerAuthenticationConverter.convert(exchange)
    |      Mono.empty()              => do not attempt authentication
    |      Mono.error(AuthException) => authentication failure
    |      Mono.just(candidate)      => candidate.isAuthenticated() = false
    |
    +-- ReactiveAuthenticationManager.authenticate(candidate)
    |      Mono.empty()              => manager does not handle candidate
    |      Mono.error(AuthException) => authentication failure
    |      Mono.just(verified)       => verified.isAuthenticated() = true
    |
    +-- SecurityContextRepository / Reactor Context
    |      NoOp: do not persist across other requests
    |      WebSession: can store and load from cookie/session
    |
    +-- success handler: continue chain or actively finalize response
    |      v
    +-- AuthorizationWebFilter: .authenticated(), .hasAuthority(...)
    |      v
    +-- Controller -> Service -> data permission
    |
    v
HTTP response
```

This is a **logical diagram**, not a literal trace of the exact internal call sequence. For WebFlux, Spring places the `Authentication` into the current subscriber's **Reactor Context**. Do not set an arbitrary `ThreadLocal` variable or exchange attribute and expect `authorizeExchange` to understand it.

### 2.1. Responsibilities of Each Component

| Component | Responsible For | Must Not Do |
| --- | --- | --- |
| `ServerWebExchangeMatcher` | Selecting paths/methods where AuthN should be attempted | Checking secrets, fabricating roles |
| `ServerAuthenticationConverter` | Parsing credential/syntax from the request, building a candidate | Returning a trusted token before verification |
| `ReactiveAuthenticationManager` | Verifying the credential, building principal + authorities from server data | Blocking JDBC/event loop or failing open |
| `ServerAuthenticationSuccessHandler` | Continuing the chain or finalizing a valid login response | Unintentionally bypassing authorization |
| `ServerAuthenticationFailureHandler` | Finalizing a failed AuthN result | Echoing raw credentials/stack traces |
| `ServerAuthenticationEntryPoint` | Challenging when a resource requires auth and the request is unauthenticated | Treating a missing-key request as success |
| `ServerSecurityContextRepository` | Saving/loading security context across requests if needed | Accidentally creating sessions for a stateless API |
| `authorizeExchange` | Checking authority, role, pattern, method | Replacing tenant/record ownership checks |

Use `AuthenticationWebFilter` from `org.springframework.security.web.server.authentication`. Do not confuse it with Servlet `AuthenticationFilter` or `UsernamePasswordAuthenticationFilter`; WebFlux uses `ServerHttpSecurity`/`SecurityWebFilterChain`, not `HttpSecurity`/Servlet FilterChain.

### 2.2. Mono.empty and Mono.error Are Very Different

In the converter:

```java
return Mono.empty(); // No credential of the type this converter recognizes
return Mono.just(candidate); // Credential present, correctness not yet checked
return Mono.error(new BadCredentialsException("Malformed credential"));
```

If it returns `Mono.empty()`, the filter does not attempt further authentication. The request proceeds; a route requiring `.authenticated()` must still return **401** via authorization/entry point. If a route is accidentally `permitAll()`, empty will let the request pass — which is why **deny by default** matters.

If the credential is recognized by the scheme but invalid, the manager must return:

```java
return Mono.error(new BadCredentialsException("Invalid credential"));
```

**Do not** return `Mono.empty()` to mask a wrong key/password for a scheme you support. Empty in a manager normally means **this manager does not support that candidate type**, enabling intentional chaining of multiple managers.

### 2.3. Trusted Result

Only create an authenticated token after verifying:
- Secret/key/digest;
- Key status is active, not revoked/expired;
- Registered client/tenant/scope/audience;
- Correct credential format and token type;
- Additional conditions such as mTLS binding or signed requests if required by the protocol.

The authorization manager must use **GrantedAuthority** mapped by the server, not `roles=admin` read from a caller-supplied header.

## 3. Choose the Authentication Style Before Writing Code

There are two common models.

**Per-request stateless API**: Every request sends `Authorization: DemoKey ...`. `AuthenticationWebFilter` verifies the key each time or via a properly lifecycle-managed cache; the result is not saved in a session. A subsequent request without the key still gets 401. Use `NoOpServerSecurityContextRepository`.

**Interactive session login**: A `POST /session/login` request verifies a password/OTP/assertion and creates a session. The browser sends a session cookie on subsequent requests. Use `WebSessionServerSecurityContextRepository` and protect cookies/CSRF/session fixation/logout. The success handler typically redirects or returns a login response, unlike the chain-continuing success handler of an API key.

**Choose one clear contract**; do not accidentally turn an API key into cookie-based login. Spring Security's `AuthenticationWebFilter` defaults to `NoOpServerSecurityContextRepository`; if you want to persist login, you must change the repository on the filter itself **and** configure where the SecurityContext is loaded.

## 4. Designing the `Authorization: DemoKey ...` Demo

The client sends:

```http
GET /api/whoami HTTP/1.1
Host: localhost:8080
Authorization: DemoKey local-example-token
```

The name `DemoKey` is used solely to make the custom converter obvious. A real API key is a **bearer secret** that must be transmitted over HTTPS, have sufficient entropy, and have a lifecycle covering creation, provisioning, rotation, revocation, expiration, misuse monitoring, and tenant/scope policy. Do not pass it via `?api_key=...` because query parameters are recorded in logs/history/referrer headers.

**Header Classification:**
- No Authorization header → converter returns empty → protected route returns 401.
- Authorization with `Basic`/`Bearer` scheme → DemoKey converter does not handle it → protected route still returns 401 when no other mechanism applies.
- `DemoKey correct-secret` → unauthenticated candidate → manager verifies → trusted principal.
- `DemoKey wrong-secret` → manager emits BadCredentials → 401.
- Malformed `DemoKey` (blank, too long, contains illegal whitespace) → converter emits BadCredentials → 401.
- Two Authorization headers → reject to avoid ambiguity and prevent header smuggling.

In production with multiple auth schemes, a converter returning empty must be paired with **separate matchers/chains**, never letting a weaker fallback mechanism produce unintended authentication.

## 5. Runnable Java 17+ / Spring Boot WebFlux Project

Directory tree:

```text
custom-auth-webflux/
  settings.gradle
  build.gradle
  src/main/resources/application.yml
  src/main/java/example/customauth/
    CustomAuthApplication.java
    ApiKeyPrincipal.java
    ApiKeyAuthenticationToken.java
    DemoKeyServerAuthenticationConverter.java
    DemoKeyReactiveAuthenticationManager.java
    SecurityConfig.java
    CurrentCallerService.java
    OrderService.java
    DemoController.java
  src/test/java/example/customauth/
    CustomAuthApplicationTests.java
    AuthenticationManagerTests.java
```

The example has one partner `partner-a` in `tenant-a` with `SCOPE_orders:read`. The demo database is an in-memory `Map` to keep the focus on the filter; production must replace it with a proper store and policy. The secret is read only from the `DEMO_API_KEY` environment variable and never committed.

### 5.1. settings.gradle

```groovy
rootProject.name = 'custom-auth-webflux'
```

### 5.2. build.gradle

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
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Do not use Servlet `spring-boot-starter-web` and do not copy Servlet `AuthenticationFilter`/`HttpSecurity`. The Spring Boot 3.3.13 BOM manages compatible Spring Security 6.3.x, Netty, and Reactor versions. For new projects, prefer a currently maintained release; this example is pinned for lab reproducibility.

### 5.3. application.yml

```yaml
server:
  port: 8080

demo:
  api-key: "${DEMO_API_KEY:}"
```

If `DEMO_API_KEY` is absent, the value is blank and the AuthenticationManager bean will refuse to start. This is **fail closed** instead of accepting an empty credential. In unit/integration tests, this property is supplied via `@SpringBootTest(properties = ...)`. Never store production secrets in YAML.

### 5.4. CustomAuthApplication.java

```java
package example.customauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CustomAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(CustomAuthApplication.class, args);
    }
}
```

### 5.5. ApiKeyPrincipal.java

```java
package example.customauth;

public record ApiKeyPrincipal(String clientId, String tenantId) {
}
```

The principal holds only the **verified public/tenant identity**, never the raw key. An immutable Java 17 record keeps the data explicit. A single partner's keys can carry different authorities depending on server policy.

### 5.6. ApiKeyAuthenticationToken.java

```java
package example.customauth;

import java.util.Collection;
import java.util.List;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;

public final class ApiKeyAuthenticationToken
        extends AbstractAuthenticationToken {

    private final Object principal;
    private Object credentials;

    private ApiKeyAuthenticationToken(
            Object principal,
            Object credentials,
            Collection<? extends GrantedAuthority> authorities,
            boolean verified) {
        super(authorities);
        this.principal = principal;
        this.credentials = credentials;
        super.setAuthenticated(verified);
    }

    public static ApiKeyAuthenticationToken presented(String key) {
        return new ApiKeyAuthenticationToken(
                null, key, List.of(), false);
    }

    public static ApiKeyAuthenticationToken verified(
            ApiKeyPrincipal principal,
            Collection<? extends GrantedAuthority> authorities) {
        return new ApiKeyAuthenticationToken(
                principal, null, authorities, true);
    }

    @Override
    public Object getPrincipal() {
        return principal;
    }

    @Override
    public Object getCredentials() {
        return credentials;
    }

    @Override
    public String getName() {
        if (principal instanceof ApiKeyPrincipal p) {
            return p.clientId();
        }
        return "unverified-key";
    }

    @Override
    public void setAuthenticated(boolean authenticated) {
        if (authenticated) {
            throw new IllegalArgumentException(
                    "Use verified factory after authentication");
        }
        super.setAuthenticated(false);
    }

    @Override
    public void eraseCredentials() {
        super.eraseCredentials();
        credentials = null;
    }
}
```

Explanation:
1. `presented` creates a candidate with `isAuthenticated=false` and the raw credential only in `credentials`.
2. `verified` creates a new Authentication with the verified principal, server-assigned authorities, and `credentials=null`.
3. Callers must not set `isAuthenticated=true` directly; overriding `setAuthenticated` blocks this. The private constructor calls `super.setAuthenticated(verified)` via internal factories.
4. `getName()` on a verified token returns `clientId`, not the secret.
5. `eraseCredentials()` clears the internal reference, though Java `String` instances and request headers may remain in memory until GC; **protect all logs/traces/heap dumps** and do not treat erasing as guaranteed physical zeroing.
6. Because the `verified(...)` factory is public for the demo manager to call, a real codebase should restrict trusted call sites via package/module visibility or design review; never let request handlers construct verified tokens arbitrarily.

### 5.7. DemoKeyServerAuthenticationConverter.java

```java
package example.customauth;

import java.util.List;
import org.springframework.http.HttpHeaders;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.server.authentication.ServerAuthenticationConverter;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
public class DemoKeyServerAuthenticationConverter
        implements ServerAuthenticationConverter {

    @Override
    public Mono<Authentication> convert(ServerWebExchange exchange) {
        List<String> values = exchange.getRequest()
                .getHeaders().get(HttpHeaders.AUTHORIZATION);

        if (values == null || values.isEmpty()) {
            return Mono.empty();
        }
        if (values.size() != 1) {
            return Mono.error(new BadCredentialsException(
                    "Ambiguous Authorization headers"));
        }

        String header = values.get(0);
        int space = header.indexOf(' ');

        if (space < 0 ||
                !header.substring(0, space)
                        .equalsIgnoreCase("DemoKey")) {
            return Mono.empty();
        }

        String key = header.substring(space + 1);
        if (key.isBlank() || key.length() > 256
                || key.indexOf(' ') >= 0
                || key.indexOf('\t') >= 0) {
            return Mono.error(new BadCredentialsException(
                    "Malformed DemoKey credential"));
        }

        return Mono.just(ApiKeyAuthenticationToken.presented(key));
    }
}
```

The converter handles **HTTP syntax**; it does not know whether the key is right or wrong. If a properly formatted DemoKey header is present, it sends a candidate to the manager. If the header is missing or uses Basic/Bearer, it returns empty; `authorizeExchange` ensures protected APIs do not return 200. A DemoKey header without a space is also ignored and subsequently receives 401 from the entry point on protected routes.

**Header normalization:** Some proxies merge duplicate headers into a single comma-separated string. The lab converter still rejects strings with invalid whitespace, but production must have a clear gateway policy for duplicate/smuggling headers rather than relying on a single count check.

Never put the raw key into logs or error messages. Do not read the key from query parameters or a JSON body for this style of API request authentication.

### 5.8. DemoKeyReactiveAuthenticationManager.java

```java
package example.customauth;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class DemoKeyReactiveAuthenticationManager
        implements ReactiveAuthenticationManager {

    private final byte[] expectedDigest;

    public DemoKeyReactiveAuthenticationManager(
            @Value("${demo.api-key}") String expectedKey) {
        if (expectedKey == null || expectedKey.isBlank()) {
            throw new IllegalStateException(
                    "DEMO_API_KEY must be set");
        }
        expectedDigest = hash(expectedKey);
    }

    @Override
    public Mono<Authentication> authenticate(Authentication candidate) {
        if (!(candidate instanceof ApiKeyAuthenticationToken token)
                || candidate.isAuthenticated()) {
            return Mono.empty();
        }

        Object raw = token.getCredentials();
        if (!(raw instanceof String key) || key.isBlank()) {
            return Mono.error(new BadCredentialsException("Invalid API key"));
        }

        return Mono.fromSupplier(
                        () -> MessageDigest.isEqual(
                                hash(key), expectedDigest))
                .flatMap(valid -> {
                    if (!valid) {
                        return Mono.<Authentication>error(
                                new BadCredentialsException(
                                        "Invalid API key"));
                    }
                    return Mono.<Authentication>just(
                            ApiKeyAuthenticationToken.verified(
                                    new ApiKeyPrincipal(
                                            "partner-a", "tenant-a"),
                                    List.of(new SimpleGrantedAuthority(
                                            "SCOPE_orders:read"))));
                });
    }

    private static byte[] hash(String value) {
        try {
            return MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 unavailable", exception);
        }
    }
}
```

**Key points to understand:**

- The manager accepts only unverified `ApiKeyAuthenticationToken` candidates. Any other type returns `Mono.empty()` so this manager skips it. A wrong key for this scheme must emit `BadCredentialsException`, **never empty**.
- The server compares digests with `MessageDigest.isEqual` to mitigate timing leakage during comparison. SHA-256 is appropriate when keys are **random with high entropy**; do not use a plain fast hash for user-chosen passwords.
- Principal/tenant/scope are assigned by the server. Never read `X-Role: ADMIN`, `X-Tenant`, or `scope` from client-supplied headers to grant permissions.
- `Mono.fromSupplier` defers the fast hash computation until subscription; it does not perform blocking database I/O on the event loop.
- If verifying keys via blocking JDBC/LDAP/KMS, use a reactive client or `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` with bounded concurrency and timeouts; never block directly before returning the Mono.
- Production requires key IDs, a multi-key identity store, revocation/expiry/rotation, quotas, auditing, cache invalidation, and a secret manager; a single key in env is only for the lab.

### 5.9. SecurityConfig.java

```java
package example.customauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authentication.AuthenticationWebFilter;
import org.springframework.security.web.server.authentication.ServerAuthenticationEntryPointFailureHandler;
import org.springframework.security.web.server.authentication.WebFilterChainServerAuthenticationSuccessHandler;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            DemoKeyReactiveAuthenticationManager manager,
            DemoKeyServerAuthenticationConverter converter) {

        var noSession =
                NoOpServerSecurityContextRepository.getInstance();

        ServerAuthenticationEntryPoint entryPoint =
                (exchange, exception) -> {
                    var response = exchange.getResponse();
                    response.setStatusCode(HttpStatus.UNAUTHORIZED);
                    response.getHeaders().set(
                            HttpHeaders.WWW_AUTHENTICATE,
                            "DemoKey realm=\"learning-api\"");
                    return response.setComplete();
                };

        AuthenticationWebFilter filter =
                new AuthenticationWebFilter(manager);

        filter.setRequiresAuthenticationMatcher(
                new PathPatternParserServerWebExchangeMatcher(
                        "/api/**"));
        filter.setServerAuthenticationConverter(converter);
        filter.setSecurityContextRepository(noSession);
        filter.setAuthenticationSuccessHandler(
                new WebFilterChainServerAuthenticationSuccessHandler());
        filter.setAuthenticationFailureHandler(
                new ServerAuthenticationEntryPointFailureHandler(
                        entryPoint));

        return http
                .securityContextRepository(noSession)
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(
                                HttpMethod.GET, "/public/ping")
                        .permitAll()
                        .pathMatchers(
                                HttpMethod.GET, "/api/whoami")
                        .authenticated()
                        .pathMatchers(
                                HttpMethod.GET, "/api/orders/**")
                        .hasAuthority("SCOPE_orders:read")
                        .anyExchange().denyAll())
                .httpBasic(basic -> basic.disable())
                .formLogin(form -> form.disable())
                .logout(logout -> logout.disable())
                // For stateless header-only API in this lab only:
                .csrf(csrf -> csrf.disable())
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint(entryPoint))
                .addFilterAt(
                        filter, SecurityWebFiltersOrder.AUTHENTICATION)
                .build();
    }
}
```

**Wiring explanation:**

1. `new AuthenticationWebFilter(manager)` takes a `ReactiveAuthenticationManager`, not a Servlet `AuthenticationManager`.
2. `setRequiresAuthenticationMatcher("/api/**")` only attempts credential parsing on API paths; `/public/ping` is untouched by the custom filter.
3. `setServerAuthenticationConverter(converter)` replaces the default Basic converter in `AuthenticationWebFilter`; without it, the filter will not understand DemoKey.
4. `setSecurityContextRepository(NoOp...)` ensures the custom filter does not persist `Authentication` to subsequent requests; `http.securityContextRepository(noSession)` aligns the context-loading mechanism.
5. `WebFilterChainServerAuthenticationSuccessHandler` continues the filter chain so `AuthorizationWebFilter` runs after AuthN. If a success handler returns 204 early, it can prevent the controller from running.
6. `ServerAuthenticationEntryPointFailureHandler` turns wrong/malformed keys into 401. `exceptionHandling.authenticationEntryPoint` handles missing keys as 401 when authorization detects an unauthenticated request.
7. `WWW-Authenticate: DemoKey realm="learning-api"` here is a challenge for the lab scheme, not standardized `Bearer` or `Basic`.
8. `SecurityWebFiltersOrder.AUTHENTICATION` places the filter inside the Spring Security chain before authorization. Do not also register the filter as a global `WebFilter` bean to avoid double execution.
9. `authorizeExchange` protects whoami with `authenticated`, protects orders by authority, and denies other URLs/methods.
10. `httpBasic`, `formLogin`, and `logout` are disabled for this DemoKey-only lab; avoid leaving another Basic filter active that might accept user/password unintentionally.
11. `csrf.disable()` **only makes sense if this is genuinely a stateless API without browser auto-sent session/cookies**. When browser login exists, enable CSRF and split security chains.
12. This design uses no cookies for authentication. A subsequent request without the header still gets 401 even if the previous request returned 200.

### 5.10. CurrentCallerService.java

```java
package example.customauth;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class CurrentCallerService {

    public Mono<Caller> requireCaller() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .switchIfEmpty(Mono.error(
                        new AccessDeniedException(
                                "Authentication required")))
                .flatMap(auth -> {
                    if (!auth.isAuthenticated()
                            || !(auth.getPrincipal()
                                    instanceof ApiKeyPrincipal principal)) {
                        return Mono.error(new AccessDeniedException(
                                "Verified API client required"));
                    }

                    return Mono.just(new Caller(
                            principal.clientId(),
                            principal.tenantId()));
                });
    }

    public record Caller(String clientId, String tenantId) {}
}
```

The service reads `Authentication` from the subscriber's **Reactor Context**; it never calls Servlet ThreadLocal `SecurityContextHolder.getContext()` and never calls `block()` or `subscribe()` manually. The method fails closed if the context is missing or the principal is not an `ApiKeyPrincipal`; this provides an extra layer of defense when the service is reused in environments with multiple auth mechanisms.

If the domain layer should remain independent of Spring, it can receive an immutable `Caller` from the authenticated application boundary rather than accepting a `Caller` DTO directly declared by the HTTP client.

### 5.11. OrderService.java

```java
package example.customauth;

import java.util.Map;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class OrderService {

    private final CurrentCallerService callerService;

    private final Map<String, Order> orders = Map.of(
            "A-100", new Order(
                    "A-100", "tenant-a", "partner-a", "READY"),
            "A-101", new Order(
                    "A-101", "tenant-a", "partner-b", "PAID"),
            "B-200", new Order(
                    "B-200", "tenant-b", "partner-a", "PENDING"));

    public OrderService(CurrentCallerService callerService) {
        this.callerService = callerService;
    }

    public Mono<OrderView> readOwned(String id) {
        return callerService.requireCaller()
                .flatMap(caller -> Mono.justOrEmpty(orders.get(id))
                        .filter(order ->
                                order.tenantId().equals(caller.tenantId())
                                && order.ownerId().equals(caller.clientId()))
                        .map(order -> new OrderView(
                                order.id(), order.status())));
    }

    private record Order(
            String id, String tenantId, String ownerId,
            String status) {
    }

    public record OrderView(String id, String status) {}
}
```

The manager authenticates `partner-a/tenant-a`, so:
- `A-100` returns 200;
- `A-101` returns 404 because of a different owner;
- `B-200` returns 404 because of a different tenant.

In a real database, use R2DBC prepared/bind parameters and **put tenant+owner in the WHERE clause**:

```sql
SELECT id, status
FROM orders
WHERE id = :orderId
  AND tenant_id = :verifiedTenantId
  AND owner_id = :verifiedClientId;
```

Do not query by `id` alone and return the entity before checking the tenant. An API key with `SCOPE_orders:read` only permits the action type, not reading orders belonging to any tenant.

### 5.12. DemoController.java

```java
package example.customauth;

import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    private final CurrentCallerService callers;
    private final OrderService orders;

    public DemoController(
            CurrentCallerService callers, OrderService orders) {
        this.callers = callers;
        this.orders = orders;
    }

    @GetMapping("/public/ping")
    public Map<String, String> ping() {
        return Map.of("message", "PONG");
    }

    @GetMapping("/api/whoami")
    public Mono<CurrentCallerService.Caller> whoami() {
        return callers.requireCaller();
    }

    @GetMapping("/api/orders/{id}")
    public Mono<OrderService.OrderView> order(@PathVariable String id) {
        return orders.readOwned(id)
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                                HttpStatus.NOT_FOUND,
                                "Order not found")));
    }
}
```

No code in the controller reads the raw API key. The filter already authenticated before reaching the controller; the service also verifies the principal type. The `whoami` JSON contains only `clientId`/`tenantId`, never the raw key or `Authentication.getCredentials()`.

### 5.13. Running the Demo

Requires JDK 17+ and Gradle compatible with Boot 3.3.13. Linux/macOS:

```bash
export DEMO_API_KEY='local-example-only-demo-key'
gradle bootRun
```

Windows PowerShell:

```powershell
$env:DEMO_API_KEY = "local-example-only-demo-key"
gradle bootRun
```

If using the Gradle Wrapper, run `./gradlew bootRun` or `gradlew.bat bootRun`. This run command is for localhost only; **never send the demo credential over the public Internet**.

Test the public endpoint:

```bash
curl -i http://localhost:8080/public/ping
```

Expected 200:

```json
{"message":"PONG"}
```

Without a key:

```bash
curl -i http://localhost:8080/api/whoami
```

Expected 401 and header:

```http
WWW-Authenticate: DemoKey realm="learning-api"
```

With the valid key:

```bash
curl -i -H 'Authorization: DemoKey local-example-only-demo-key' \
  http://localhost:8080/api/whoami
```

Expected:

```json
{"clientId":"partner-a","tenantId":"tenant-a"}
```

Read orders with matching/mismatching owners:

```bash
curl -i -H 'Authorization: DemoKey local-example-only-demo-key' \
  http://localhost:8080/api/orders/A-100

curl -i -H 'Authorization: DemoKey local-example-only-demo-key' \
  http://localhost:8080/api/orders/A-101

curl -i -H 'Authorization: DemoKey local-example-only-demo-key' \
  http://localhost:8080/api/orders/B-200
```

Expected results: 200/404/404. Body for `A-100`:

```json
{"id":"A-100","status":"READY"}
```

Wrong key:

```bash
curl -i -H 'Authorization: DemoKey wrong-key' \
  http://localhost:8080/api/whoami
```

Expected 401, without echoing the key. On PowerShell, use `curl.exe` if you need exact Unix curl syntax; `Invoke-WebRequest` uses its own header dictionary API. Shell history/process arguments can record raw credentials, so use only the demo key in the lab.

**These are expected outputs from the code**, not a claim that a live server was executed outside this lesson.

## 6. Integration Testing with WebTestClient

Create `src/test/java/example/customauth/CustomAuthApplicationTests.java`:

```java
package example.customauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK,
        properties = "demo.api-key=integration-test-key")
@AutoConfigureWebTestClient
class CustomAuthApplicationTests {

    private static final String GOOD = "DemoKey integration-test-key";

    @Autowired
    WebTestClient client;

    @Test
    void publicRouteWorksWithoutCredential() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("PONG");
    }

    @Test
    void noCredentialIs401() {
        client.get().uri("/api/whoami")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueEquals(
                        HttpHeaders.WWW_AUTHENTICATE,
                        "DemoKey realm=\"learning-api\"");
    }

    @Test
    void correctKeyGivesOnlyMinimalPublicIdentity() {
        client.get().uri("/api/whoami")
                .header(HttpHeaders.AUTHORIZATION, GOOD)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.clientId").isEqualTo("partner-a")
                .jsonPath("$.tenantId").isEqualTo("tenant-a")
                .jsonPath("$.credentials").doesNotExist();
    }

    @Test
    void wrongKeyIs401() {
        client.get().uri("/api/whoami")
                .header(HttpHeaders.AUTHORIZATION,
                        "DemoKey wrong-key")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void emptyKeyIs401() {
        client.get().uri("/api/whoami")
                .header(HttpHeaders.AUTHORIZATION, "DemoKey ")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void basicOrBearerAreNotDemoKey() {
        client.get().uri("/api/whoami")
                .headers(h -> h.setBasicAuth("user", "pass"))
                .exchange()
                .expectStatus().isUnauthorized();

        client.get().uri("/api/whoami")
                .header(HttpHeaders.AUTHORIZATION,
                        "Bearer fake-jwt")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void multipleAuthorizationHeadersAreRejected() {
        client.get().uri("/api/whoami")
                .header(HttpHeaders.AUTHORIZATION, GOOD, GOOD)
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void ownedOrderCanBeRead() {
        client.get().uri("/api/orders/A-100")
                .header(HttpHeaders.AUTHORIZATION, GOOD)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo("A-100");
    }

    @Test
    void anotherPartnerOrderIsNotVisible() {
        client.get().uri("/api/orders/A-101")
                .header(HttpHeaders.AUTHORIZATION, GOOD)
                .exchange()
                .expectStatus().isNotFound();
    }

    @Test
    void anotherTenantOrderIsNotVisible() {
        client.get().uri("/api/orders/B-200")
                .header(HttpHeaders.AUTHORIZATION, GOOD)
                .exchange()
                .expectStatus().isNotFound();
    }

    @Test
    void postNotEnabledEvenWithKey() {
        client.post().uri("/api/whoami")
                .header(HttpHeaders.AUTHORIZATION, GOOD)
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void requestDoesNotPersistLoginForNextRequest() {
        client.get().uri("/api/whoami")
                .header(HttpHeaders.AUTHORIZATION, GOOD)
                .exchange()
                .expectStatus().isOk();

        client.get().uri("/api/whoami")
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
```

Run:

```bash
gradle test
```

**Limitations:** `WebTestClient` tests the Spring Security HTTP pipeline, but it does not prove production HTTPS, rotation/revocation, rate limits, or trust of an external identity provider. The duplicate header test depends on how the mock HTTP client represents values; at a real gateway you must also test proxy-merged duplicates.

## 7. Testing the Manager Standalone with StepVerifier

Create `src/test/java/example/customauth/AuthenticationManagerTests.java`:

```java
package example.customauth;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.TestingAuthenticationToken;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AuthenticationManagerTests {

    private final DemoKeyReactiveAuthenticationManager manager =
            new DemoKeyReactiveAuthenticationManager("expected-key");

    @Test
    void candidateIsNotAuthenticated() {
        var token = ApiKeyAuthenticationToken.presented("expected-key");
        assertFalse(token.isAuthenticated());
        assertThrows(IllegalArgumentException.class,
                () -> token.setAuthenticated(true));
    }

    @Test
    void correctKeyCreatesVerifiedPrincipalWithoutCredential() {
        StepVerifier.create(manager.authenticate(
                ApiKeyAuthenticationToken.presented("expected-key")))
                .assertNext(auth -> {
                    assertTrue(auth.isAuthenticated());
                    assertNull(auth.getCredentials());
                    assertEquals("partner-a", auth.getName());
                    assertTrue(auth.getAuthorities().stream()
                            .anyMatch(a -> a.getAuthority()
                                    .equals("SCOPE_orders:read")));
                })
                .verifyComplete();
    }

    @Test
    void wrongKeyFailsInsteadOfEmpty() {
        StepVerifier.create(manager.authenticate(
                ApiKeyAuthenticationToken.presented("wrong")))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void unsupportedAuthenticationTypeReturnsEmpty() {
        StepVerifier.create(manager.authenticate(
                new TestingAuthenticationToken("user", "secret")))
                .verifyComplete();
    }
}
```

Manager tests make clear:
- A candidate cannot mark itself as verified.
- A valid secret produces a new Authentication with null credentials and server-assigned authorities.
- A wrong key emits `BadCredentialsException` instead of `Mono.empty()`.
- An unsupported token type returns `Mono.empty()`.
- No Spring Context is needed for pure manager tests, saving execution time.

You can test `CurrentCallerService` separately with:

```java
// Illustrative TEST SNIPPET, requires importing classes/Assertions.
var verified = ApiKeyAuthenticationToken.verified(
        new ApiKeyPrincipal("partner-a", "tenant-a"),
        java.util.List.of(
                new org.springframework.security.core.authority
                        .SimpleGrantedAuthority("SCOPE_orders:read")));

StepVerifier.create(new CurrentCallerService()
        .requireCaller()
        .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(verified)))
        .assertNext(caller -> assertEquals(
                "partner-a", caller.clientId()))
        .verifyComplete();
```

The snippet above is not a standalone runnable file: it requires importing `StepVerifier`, `ReactiveSecurityContextHolder`, and `assertEquals`. A similar test for a missing context should expect `AccessDeniedException`. Never use ThreadLocal `SecurityContextHolder` in a WebFlux service.

## 8. Short Test Matrix to Verify Paths

| HTTP request | Converter | Manager | Authorization | Expected Result |
| --- | --- | --- | --- | --- |
| GET `/public/ping` no header | No match | No | permitAll | 200 |
| GET `/api/whoami` no key | Empty | No | unauthenticated | 401 |
| GET `/api/whoami` valid key | Candidate | verified | authenticated | 200 |
| GET `/api/whoami` wrong key | Candidate | BadCredentials | failure handler | 401 |
| GET `/api/whoami` Basic | Empty | No | unauthenticated | 401 |
| GET `/api/orders/A-100` valid key | Candidate | verified, scope read | own order | 200 |
| GET `/api/orders/A-101` valid key | Candidate | verified, scope read | different owner | 404 |
| GET `/api/orders/B-200` valid key | Candidate | verified, scope read | different tenant | 404 |
| POST `/api/whoami` valid key | Candidate | verified | denyAll | 403 |
| GET `/api/whoami` after previous authed request but no key | Empty | No | NoOp/unauthenticated | 401 |

Do not assume every nonexistent route returns 404: if `anyExchange().denyAll()` runs before the handler, an authenticated caller may receive 403 per policy. With multi-chain setups or custom filters/handlers, results should be verified against your environment.

## 9. Choosing Stateless or WebSession Properly

### 9.1. Stateless NoOp

In the example:
- `filter.setSecurityContextRepository(noSession)`;
- `http.securityContextRepository(noSession)`;
- Each HTTP request with a key authenticates on its own;
- Without a key, no prior Authentication is inherited.

Other framework components may still create a `WebSession` for their own purposes; what matters is that **SecurityContext authentication is not persisted between requests**, not a guarantee that zero session objects exist anywhere in the application.

### 9.2. Stateful Form Login

If you genuinely want to persist login after a `POST /session/login` request, you can use:

```java
// CONFIG SNIPPET: illustrates architectural change only.
var repository =
        new WebSessionServerSecurityContextRepository();

filter.setSecurityContextRepository(repository);
http.securityContextRepository(repository);
```

However, you must change the matcher to the login processing URL, the converter to parse form/body credentials, the success/failure handlers to perform valid redirects/JSON responses, and add:
- CSRF tokens for state-changing browser requests;
- Secure/HttpOnly/SameSite cookies;
- session fixation protection;
- logout/invalidation;
- session timeout/rotation;
- a shared store when running multiple nodes;
- open-redirect prevention after login.

**Do not copy those two lines into a per-request API key flow unless you actually want browsers to call the API without an Authorization header after a single authentication.**

### 9.3. Different Success Handlers

**Per-request API:** use `WebFilterChainServerAuthenticationSuccessHandler` so the request proceeds down to `AuthorizationWebFilter` and then the controller.

**Login endpoint:** you can choose a success handler that terminates with 200/204 or a redirect, because it is a dedicated login action. Applying a 204-terminating handler to a filter accepting credentials across **all `/api/**`** will block every valid-key request before the controller; order-based authorization will not run as expected.

### 9.4. Failure Handler and Entry Point

The failure handler handles **failed authentication attempts**. The entry point handles **unauthenticated requests to resources requiring auth**. A missing header typically causes the converter to return empty, **never entering the failure handler**; therefore the entry point must return 401.

A minimal 401:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: DemoKey realm="learning-api"
```

Do not echo a body containing secrets, policy details, or stack traces. 403 is reserved for an authenticated principal lacking authority, not used in place of 401 for every invalid key.

## 10. Multiple SecurityWebFilterChains and Coordinating Mechanisms

A real-world application may have:
- `/api/partners/**` using API key/mTLS;
- `/api/clients/**` using JWT bearer;
- `/web/**` using OIDC session login;
- `/public/**` permitAll.

With multiple `SecurityWebFilterChain` beans, Spring Security picks the **first chain that matches the request**; it does not run all three by default.

```java
// ARCHITECTURE SNIPPET, not standalone runnable.
@Bean
@Order(1)
SecurityWebFilterChain partners(ServerHttpSecurity http) {
    return http.securityMatcher(
            new PathPatternParserServerWebExchangeMatcher(
                    "/api/partners/**"))
            // addFilterAt(customFilter, AUTHENTICATION)
            // authorizeExchange ...
            .build();
}

@Bean
@Order(2)
SecurityWebFilterChain others(ServerHttpSecurity http) {
    return http.securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/**"))
            // oauth2ResourceServer, oauth2Login or rules...
            .build();
}
```

This is a fragment and cannot be copied verbatim as a runnable project; wire the corresponding filters, beans, and policies. In production:
1. Match narrower chains before broader chains.
2. Test start/callback/login/API paths for each mechanism.
3. Do not let the `/**` chain hijack requests meant for the partner filter.
4. Ensure CORS/preflight goes through the chain/policy that handles it properly.
5. Do not feed DemoKey candidates into a JWT manager or vice versa.

If a single chain genuinely supports multiple token types, look into `DelegatingServerAuthenticationConverter`, `DelegatingReactiveAuthenticationManager`, and `ReactiveAuthenticationManagerResolver<ServerWebExchange>`. When a credential is recognized but **wrong**, never silently downgrade to a weaker scheme.

**Avoid global double registration:** Declaring an `AuthenticationWebFilter` as a `WebFilter` bean can cause WebFlux to register it globally, and then `addFilterAt` inserts it again, causing it to execute twice. The demo instantiates the filter **inside the `SecurityWebFilterChain` bean** rather than declaring it as a global component.

## 11. CSRF, CORS, HTTPS, and Trust Boundaries

### 11.1. CSRF

In a stateless API where clients explicitly attach an Authorization header, you may consider disabling CSRF **for that chain alone** after verifying no browser auto-sent cookies or session credentials exist. For form login or cookie authentication, however, CSRF protection is required on state-changing requests. Using OAuth2/OIDC also does not automatically replace CSRF protection for cookie-backed mutations.

### 11.2. CORS Preflight

Browsers making cross-origin calls with an Authorization header typically send an `OPTIONS` preflight **without the actual key**. If the `/api/**` matcher catches OPTIONS and `anyExchange().denyAll()` rejects it before CORS runs, the browser will report a CORS error.

Solution: configure `CorsWebFilter` or `ServerHttpSecurity.cors(...)` with an allowlist of origins, methods, and headers, processing preflight before the authentication filter. Never arbitrarily enable `Access-Control-Allow-Origin: *` together with credentials. CORS only controls whether browser JS can read cross-origin responses; it **does not replace Authentication** and does not stop server clients using curl.

### 11.3. HTTPS

An API key is a bearer secret: anyone who obtains it can replay it. Enforce HTTPS over the Internet, trusted TLS termination/gateway, strip or overwrite untrusted headers, and restrict logging. Never trust `X-Authenticated-User`, `X-Tenant`, or `X-Role` from an external request as proof of authentication.

### 11.4. Replay and Brute Force

A long secret resists guessing, but does not prevent a **stolen key** from being abused. You need:
- CSPRNG and high key entropy;
- key ID + digest, rotation/revocation;
- expiry, least-privilege scope grants, per-key tenant;
- rate limiting, auditing, alerts;
- optional mTLS-bound tokens/DPoP or request signatures when your threat model demands it;
- replay protection via nonce/timestamp/canonicalization/anti-replay store if designing signed requests; do not merely attach an unverified timestamp.

### 11.5. Logging

Do not:

```java
log.info("Authorization={}",
        exchange.getRequest().getHeaders()
                .getFirst(HttpHeaders.AUTHORIZATION));
```

Do not enable HTTP wiretap or trace headers/bodies of token endpoints/proxies in production without redaction. Log only the event category, request ID, verified client ID/tenant alias per policy, latency, and standardized failure reason (invalid credential vs identity store unavailable); never log raw credentials, hashes, session IDs, or unnecessary emails.

## 12. ReactiveAuthenticationManager with an External Identity Store

The example manager performs fast, non-blocking SHA-256 hashing. When verifying credentials against R2DBC/Redis/IdP:

```java
// ILLUSTRATIVE SNIPPET: repository and verifyAndBuildAuth must be defined separately.
return repository.findByKeyId(keyId)
        .switchIfEmpty(Mono.error(
                new BadCredentialsException("Invalid API key")))
        .flatMap(record -> verifyAndBuildAuth(record, presentedKey));
```

You must check:
- the record exists, is active, and is not expired/revoked;
- constant-time digest/credential matching or an appropriate KDF;
- the tenant/client is still active;
- permissions come from the trusted store;
- concurrent rate limits/backpressure;
- timeouts/circuit breakers;
- cache invalidation matching your revocation SLA.

Wrong:

```java
// WRONG in WebFlux event loop:
User user = jdbcTemplate.queryForObject("SELECT ...", ...);
return Mono.just(authenticated(user));
```

The JDBC call runs **before** creating the Mono and blocks the thread. If you are forced to use a blocking SDK:

```java
// ILLUSTRATIVE SNIPPET, blockingVerifier/verifiedAuth must be defined separately.
return Mono.fromCallable(() -> blockingVerifier.verify(key))
        .subscribeOn(Schedulers.boundedElastic())
        .flatMap(result -> result.isValid()
                ? Mono.just(verifiedAuth(result))
                : Mono.error(new BadCredentialsException("Invalid key")));
```

Bound concurrency, enforce timeouts, and use a dedicated executor at high throughput; `boundedElastic` does not mean infinite resources. Never manually call `block()` or `subscribe()` inside an AuthenticationManager.

**IdP/DB outages must fail closed.** If the credential cannot be verified, never fabricate a trusted Authentication. Distinguish invalid credentials from infrastructure errors (e.g., `AuthenticationServiceException`) for metrics/alerts, while ensuring client responses leak no internals.

## 13. Production API Key Lifecycle Guide

Conceptual schema:

```text
credential_registry
  key_id
  key_digest
  client_id
  tenant_id
  granted_scopes
  status                 (active, suspended, revoked)
  expires_at
  created_at
  rotated_at
```

Flow:
1. Converter parses the auth scheme/format, extracts `key_id` if present, and enforces length limits.
2. Manager looks up by key ID via a reactive repository.
3. Verify digest, active/expiry/revocation status, and rate limits.
4. Build the authenticated principal and authorities from the server record.
5. Never store raw secrets; return only minimal identity data.
6. Resource services always check tenant/owner/permissions.
7. On revoke/rotate, invalidate caches according to policy.
8. Emit redacted metrics/audit logs without introducing a timing oracle for enumeration.

Do not use plain SHA-256 for **low-entropy passwords**; use PBKDF2/BCrypt/Argon2 and validate per policy. For high-entropy CSPRNG API keys, a SHA-256 digest may be considered alongside storage security and constant-time comparison. A public key ID is not authorization; the key secret must still be verified.

For zero-downtime rotation:
- Create a new key with its own validity window;
- Distribute via a secure secret manager;
- Allow a policy-defined overlap window if feasible;
- Monitor traffic using the old key;
- Revoke the old key on deadline;
- Execute immediate incident revocation if a key is leaked.

**If you can use OAuth2 client credentials + HTTPS/mTLS, prefer standards over inventing a new API-key protocol**. Custom filters remain useful when integrating with a legacy trust system that cannot migrate immediately.

## 14. Common Pitfalls

| Symptom | Cause | Fix |
| --- | --- | --- |
| Converter does not run | Matcher `/api/**` does not match, filter outside chain | Check `setRequiresAuthenticationMatcher` and `addFilterAt` |
| Manager does not run | Converter returned empty or errored before manager | Test convert empty/value/error |
| Wrong key still returns 200 | Manager returned verified token prematurely or route is permitAll | Fail closed, test wrong key |
| Wrong key returns 403 | Wrong entry point/failure handler or fake authenticated flag | Fix exception/401 mapping |
| Missing key still returns 200 | Rule forgot `authenticated` | Deny by default |
| Controller does not run even with valid key | Success handler terminates response early | Use `WebFilterChainServerAuthenticationSuccessHandler` |
| Request 2 does not stay logged in | NoOp repository, expected for stateless | Send key on every request or design explicit session |
| Request 2 without key still returns 200 | Accidentally saved to WebSession | Use NoOp and test stateless behavior |
| Principal is null in service | Used Servlet ThreadLocal, manual subscribe, or context lost | `ReactiveSecurityContextHolder` |
| Has `SCOPE_orders:read` but cannot read order | Tenant/owner mismatch | Check DB policy, do not bypass filter |
| CORS OPTIONS returns 401/403 | Preflight not handled before AuthN | Configure CORS on the proper chain |
| Key valid on dev but fails on prod | Different secret/rotation/env | Manage configuration per environment |
| Ambiguous duplicate header handling | Proxy normalization/smuggling | Enforce single credential and test gateway |
| 500 on auth DB failure | Blocking IO or unclassified exception | Reactive client, timeouts, fail closed |
| Auth A leaks to B | Cached static/global Authentication | Never store context shared across requests |
| Logs leak secret | Logged Authorization header/raw Authentication | Redact, restrict wiretap |
| Authenticated user has no roles | Server GrantedAuthority missing or mapper wrong | Check policy, never trust raw role header |
| Multi-chain catches wrong URL | Chain order/broad matcher | Narrow chains first, test URLs |
| Configured csrf.disable with cookie login | Removed CSRF defense | Split stateless chain and browser chain |

## 15. QA and Security Checklist

1. Only paths using the custom scheme are processed by the custom filter.
2. Input parser enforces length, format, and duplicate Authorization header limits.
3. Candidates from the client always have `isAuthenticated=false`.
4. Manager never returns authenticated when credential is wrong, revoked, expired, or the identity store is unavailable.
5. Manager uses `Mono.empty()` only for unsupported token types, never to mask wrong credentials.
6. Verified Authentication holds no raw key; principal/authorities come from the server.
7. Success handler continues the chain for per-request auth.
8. Failure handler and entry point return 401 without leaking secrets.
9. `authorizeExchange` denies by default with accurate scopes/methods.
10. Tenant/owner/record permissions are enforced in service/DB.
11. NoOp repository for per-request stateless auth; never retain Authentication across requests.
12. WebSession repository only when designing session login with CSRF/cookie/logout protections.
13. Never use Servlet ThreadLocal `SecurityContextHolder` in WebFlux.
14. Never block the event loop; auth I/O uses reactive SDKs or bounded, timed offloading.
15. Test no header, wrong header, missing key, valid key, unknown scheme, duplicate headers, wrong method, wrong tenant/owner.
16. HTTPS and proxy trust boundaries are mandatory in production.
17. Secret lifecycle includes strong generation, hashed storage, rotation, revocation, expiry, and monitoring.
18. CORS preflight has its own policy before AuthN; never use CORS as AuthN.
19. Credential values never enter URLs, response bodies, logs, metrics, traces, or exception messages.
20. Integration tests cover ingress behavior, and monitoring covers rate/latency/bulkheads for remote verifiers.

## 16. Self-Check Questions

**1. Does AuthenticationWebFilter verify the API key itself?**  
No. It coordinates the matcher/converter/manager/handlers. `ReactiveAuthenticationManager` verifies the credential.

**2. Why must you not call `setAuthenticated(true)` on a request candidate?**  
Because the credential has not been verified yet. Only a trusted manager may create an authenticated token with server-side authorities.

**3. What does a converter returning Mono.empty mean?**  
No authentication attempt is made. Protected routes must still return 401 when no Authentication is present.

**4. What should the manager return when given a wrong DemoKey?**  
`Mono.error(new BadCredentialsException(...))`, not `Mono.empty()` or a trusted token.

**5. When should a manager return empty?**  
When the manager does not support the Authentication type passed to it.

**6. Which repository does a stateless API key use?**  
`NoOpServerSecurityContextRepository.getInstance()` for both the custom filter and HTTP security context loading.

**7. Why must a second request without a key return 401 even if the first returned 200?**  
NoOp does not save authentication to subsequent requests; the key must be sent on every request.

**8. At what order must the filter be inserted?**  
`SecurityWebFiltersOrder.AUTHENTICATION`, before authorization.

**9. What does setRequiresAuthenticationMatcher do?**  
Selects requests where the filter should attempt authentication, avoiding running unnecessarily on public/login paths.

**10. How does a WebFlux service read the caller's identity?**  
`ReactiveSecurityContextHolder.getContext()` inside the reactive publisher, or by passing an immutable verified identity from the boundary.

**11. Why not use Servlet ThreadLocal SecurityContextHolder?**  
Reactor can switch threads and stores context per subscription, not in a fixed ThreadLocal.

**12. How do 401 and 403 differ?**  
401 is for missing/invalid credentials; 403 is for an authenticated principal lacking permission.

**13. What should a valid key return when accessing an order belonging to another tenant?**  
The demo returns 404, refusing to read records outside the caller's ownership.

**14. Why does CORS OPTIONS not send DemoKey?**  
Preflight only asks for cross-origin permission, not an actual API request; CORS must be processed before the auth filter.

**15. When can CSRF not be arbitrarily disabled?**  
When the application uses browser sessions/cookies or credentials automatically attached by the browser on state-changing requests.

**16. Should the expected API key be placed in application.yml?**  
No. The lab reads an environment variable; production uses a secret manager/identity store.

**17. Is SHA-256 sufficient for user-chosen passwords?**  
No. Low-entropy passwords need an adaptive KDF and rate limiting; high-entropy random API keys have a different threat model.

**18. Is tenant/owner testing still needed when scopes are present?**  
Yes. A scope defines the allowed operation type, not permission over a specific record.

**19. Why not declare AuthenticationWebFilter as a global bean and also call addFilterAt?**  
It can double-register and execute outside the intended order/security context.

**20. Should an identity store outage let old keys through to preserve availability?**  
No. If verification fails, fail closed according to policy; never fabricate an identity.

**21. If the system already has a JWT Resource Server, should it be replaced with DemoKey?**  
No. Prefer `oauth2ResourceServer().jwt()` when it fits the use case; use a custom filter only with a specific reason.

**22. How do WebTestClient and StepVerifier differ?**  
WebTestClient tests the HTTP/security chain/controller; StepVerifier tests the manager publisher and empty/error/verified transitions.

**23. Is a success handler returning 204 immediately suitable for every API key request?**  
No. It terminates before the controller when business processing is intended; use a success handler that continues the chain.

**24. Should the principal hold the key secret?**  
No. It should hold only the verified identity/tenant, with credentials nullable/erased.

**25. What is the most important factor in custom authentication?**  
Fail-closed behavior, a trusted manager as the sole place verifying credentials, server-assigned authorities, proper Reactor Context usage, scoped permissions, and negative tests.

**Remember:** In **Spring Security WebFlux**, custom authentication is structured as **matcher → converter → unauthenticated candidate → ReactiveAuthenticationManager → verified Authentication → success/failure → Reactor SecurityContext → authorization**. Always distinguish empty from error, assign authorities only from trusted sources, never leak identity across requests, never block the event loop, and enforce tenant/owner checks. `AuthenticationWebFilter` integrates a custom scheme into the chain, but **does not replace** secret lifecycle management, HTTPS, and authorization.

## References

- [Spring Security 6.3 — AuthenticationWebFilter API](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html): matcher, converter, manager, success/failure, repository.
- [Spring Security — ServerAuthenticationConverter](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/web/server/authentication/ServerAuthenticationConverter.html): conversion and `Mono.empty()`.
- [Spring Security — ServerHttpSecurity](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/config/web/server/ServerHttpSecurity.html): `addFilterAt`, `authorizeExchange`, context repository.
- [Spring Security — SecurityWebFiltersOrder](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/config/web/server/SecurityWebFiltersOrder.html): filter ordering.
- [Spring Security — NoOpServerSecurityContextRepository](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/web/server/context/NoOpServerSecurityContextRepository.html): stateless repository.
- [Spring Security — WebSessionServerSecurityContextRepository](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/web/server/context/WebSessionServerSecurityContextRepository.html): stateful repository.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `SecurityWebFilterChain`.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): Reactor Context and method authorization.
- [Spring Security — WebFlux Test](https://docs.spring.io/spring-security/reference/reactive/test/web/index.html): WebTestClient security tests.
- [Spring Security — Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): browser sessions and CSRF.
- [Spring Security — Reactive CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html): preflight before authentication.
- [Spring Framework — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): ServerWebExchange/WebFilter.
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): subscriber Context.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): auth error policy, rate limiting.
- [OWASP — REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html): HTTPS, API auth, input validation.
