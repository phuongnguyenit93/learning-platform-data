# Combining a Custom Mechanism with HTTP Basic or Bearer Tokens

> **Parent topic:** Advanced Authentication. **Stack:** Spring Security reactive / Spring WebFlux, Java 17+, Spring Boot 3.x, Spring Security 6.5.x. This lesson implements a custom API key mechanism alongside **HTTP Basic** and **OAuth2 Bearer tokens**, explaining the converter, manager, WebFilter ordering, decisions when credentials do not match or are invalid, role/scope-based authorization, testing, and operations. The example uses the custom authentication scheme `Authorization: ApiKey <key>` — an intentional demo convention, **not an OAuth2 Bearer token** or a universal API key standard for all systems.

## 1. Objectives

After this lesson, you will:

1. Understand that a WebFlux request may use **one of several mechanisms** (Basic, Bearer JWT, ApiKey), without arbitrarily chaining or falling back when authentication fails.
2. Distinguish **authentication** (verifying identity) from **authorization** (checking permissions) on the same endpoint.
3. Know that `ServerAuthenticationConverter` produces an **unauthenticated** `Authentication` object, while `ReactiveAuthenticationManager` verifies it and returns an authenticated `Authentication`.
4. Distinguish `Mono.empty()` when the scheme does not match from `Mono.error(AuthenticationException)` when the credential is recognized but invalid.
5. Configure a custom `AuthenticationWebFilter` in `SecurityWebFilterChain` without **breaking** existing HTTP Basic or JWT Resource Server support.
6. Place the filter at `SecurityWebFiltersOrder.AUTHENTICATION`, understanding why you cannot rely on ordering between two filters sharing the same order slot.
7. Protect APIs using `hasAnyAuthority` with trusted authorities issued by each distinct mechanism; a read-only API key cannot turn itself into an admin.
8. Verify 401/403 responses and reject conflicting multiple `Authorization` headers.
9. Use `WebTestClient` to test valid/invalid Basic, valid/invalid/missing-scope JWT, valid/invalid ApiKey, duplicate headers, and admin permissions.
10. Understand variants for **HTTP Basic + custom**, **Bearer + custom**, **JWT vs opaque**, and multi-chain architectures by URL.
11. Protect credentials via TLS, secret stores, key rotation, scopes, JWT issuer/audience checks, CORS/CSRF, and secret-free logs.

**Core rule:** Non-matching scheme skips the filter; matching scheme with invalid verification **fails closed**. Never silently turn a failure into an opportunity to try a weaker mechanism.

## 2. Three Types of Authorization Credentials

```http
# HTTP Basic: credentials are Base64-encoded username:password
Authorization: Basic <BASE64_CREDENTIALS>

# OAuth2 Bearer: access token issued by IdP/Authorization Server
Authorization: Bearer <ACCESS_TOKEN>

# Custom: key issued and managed by your system
Authorization: ApiKey <HIGH_ENTROPY_API_KEY>
```

**Note:** HTTP Basic Base64 **does not protect** credentials if sent over unencrypted HTTP without TLS. OAuth2 Bearer carries RFC 6750 protocol semantics and must be verified by a Resource Server via JWT signature/claims or opaque introspection. Custom ApiKey is a separate contract; never stuff an arbitrary key into Bearer to skip JWT verification.

### 2.1 Authentication Is Not Authorization

| Identity | How Authenticated | Authority After Verification | Permitted Route |
| --- | --- | --- | --- |
| `reader` | Valid Basic password | `ROLE_BASIC_READ` | `GET /api/read` |
| `administrator` | Valid Basic password | `ROLE_BASIC_READ`, `ROLE_ADMIN` | Read and `GET /api/admin` |
| `jwt-alice` | Valid Bearer JWT | `SCOPE_messages.read` | `GET /api/read` |
| `jwt-admin` | Valid Bearer JWT with admin scope | `SCOPE_api.admin` | `GET /api/admin` |
| `partner-integration` | Valid API key | `ROLE_PARTNER_READ` | `GET /api/read`, **not** admin |

A valid key does not imply all permissions; similarly, a Bearer token may be active yet lack the needed scope. The authorities above are created **only after verification by a trusted authentication source**.

### 2.2 Why Support Multiple Mechanisms?

During migrations, internal clients may still use Basic, web/mobile clients use Bearer, and certain partner integrations use API keys. You can accept them on the same endpoint once trust boundaries are evaluated, or separate URLs/security chains for clarity. Normally, prefer OAuth2 `client_credentials` for new machine clients when the ecosystem supports it rather than building an entire custom token lifecycle.

## 3. Reactive Pipeline and Related APIs

```text
HTTP Request
   |
   | Authorization: Basic / Bearer / ApiKey
   v
Spring Security SecurityWebFilterChain
   |
   +-- HTTP Basic AuthenticationWebFilter
   |      -> Basic converter -> username/password -> password encoder
   |      -> success / AuthenticationException
   |
   +-- OAuth2 Resource Server Bearer authentication
   |      -> Bearer token converter
   |      -> ReactiveJwtDecoder or ReactiveOpaqueTokenIntrospector
   |      -> success / AuthenticationException
   |
   +-- Custom AuthenticationWebFilter
   |      -> ServerAuthenticationConverter for ApiKey
   |      -> unauthenticated ApiKeyAuthenticationToken
   |      -> ApiKeyAuthenticationManager checks against server-side key
   |      -> trusted Authentication with ROLE_PARTNER_READ
   |
   v
ReactiveSecurityContextHolder / SecurityContext
   |
   v
authorizeExchange: HTTP method, path, authorities
   |
   +-- sufficient authority -> Controller
   +-- insufficient authority -> 403
   +-- unauthenticated -> 401
```

### 3.1 Class Roles

| Spring Type | Role |
| --- | --- |
| `ServerHttpSecurity` | Configures the WebFlux security chain |
| `SecurityWebFilterChain` | Selects WebFilters applied to requests |
| `AuthenticationWebFilter` | WebFilter for one type of authentication attempt |
| `ServerAuthenticationConverter` | Converts `ServerWebExchange` into an unauthenticated Authentication |
| `ReactiveAuthenticationManager` | Verifies credentials, builds principal and authorities |
| `AbstractAuthenticationToken` | Base class for creating custom Authentication objects |
| `SecurityWebFiltersOrder` | Places custom filters into the right phase |
| `ReactiveSecurityContextHolder` | Accesses SecurityContext inside Reactor Context |
| `MapReactiveUserDetailsService` | In-memory user/password store for the HTTP Basic demo |
| `ReactiveJwtDecoder` | Verifies JWTs for Bearer Resource Server |
| `ServerBearerTokenAuthenticationConverter` | Extracts Bearer tokens in WebFlux |
| `ServerAuthenticationEntryPointFailureHandler` | Delegates authentication failures to an HTTP entry point |
| `NoOpServerSecurityContextRepository` | Prevents persisting authentication in a session |

**Never use Servlet classes** such as `HttpSecurity`, `OncePerRequestFilter`, or `SecurityFilterChain` for WebFlux Netty. Reactive configuration requires `ServerHttpSecurity` and `SecurityWebFilterChain`.

### 3.2 Mono Rules for Converter and Manager

| Request Header | Custom ApiKey Converter | Manager / Downstream Handling |
| --- | --- | --- |
| No Authorization | `Mono.empty()` | No ApiKey attempt; protected endpoints will demand auth |
| `Basic ...` | `Mono.empty()` | Built-in Basic filter handles it |
| `Bearer ...` | `Mono.empty()` | OAuth2 Resource Server filter handles it |
| `ApiKey <correct>` | `Mono.just(ApiKeyAuthenticationToken.unauthenticated(key))` | Manager verifies key, issues principal |
| `ApiKey <incorrect>` | Creates unauthenticated token | Manager emits `BadCredentialsException`, returns 401 |
| `ApiKey` without value | `Mono.error(BadCredentialsException)` | 401; never downgraded to anonymous |
| Multiple Authorization header fields | Early guard rejects | 400 per demo policy |

For the manager:

- `Mono.just(authenticated)` = credential verified successfully.
- `Mono.empty()` = manager **does not support this `Authentication` type**; no decision.
- `Mono.error(AuthenticationException)` = an attempt occurred and failed. **Never convert to empty** to try a weaker provider.

### 3.3 Example of an Incorrect Fallback

```java
// DO NOT USE: swallowing authentication failure
return apiKeyManager.authenticate(input)
    .onErrorResume(ex -> basicManager.authenticate(input));
```

A wrong ApiKey credential must never be allowed to try Basic or reuse an old session. Route based on **scheme** before verification. Even with `DelegatingReactiveAuthenticationManager`, preserve `Mono.empty` for unsupported and `Mono.error` for failure; `setContinueOnError(true)` requires its own threat model and should never be enabled just to "have a fallback".

## 4. Single Chain or Multiple Security Chains?

### 4.1 One Chain for All Three Mechanisms

They can share `GET /api/read`:

```text
Authorization: Basic valid    -> ROLE_BASIC_READ -> 200
Authorization: Bearer valid   -> SCOPE_messages.read -> 200
Authorization: ApiKey valid   -> ROLE_PARTNER_READ -> 200
Invalid/malformed credential  -> 401
Valid credential, lacking scope -> 403
```

This suits migrations or endpoints that genuinely need to accept multiple client types. The trade-off is that tests and guards for scheme conflicts, duplicate headers, and authorities must be thorough.

### 4.2 Splitting Chains When Trust Boundaries Differ

Example:

```text
/internal/**  -> Basic + internal network
/api/**       -> Bearer JWT/opaque Resource Server
/partner/**   -> Custom ApiKey or OAuth2 client_credentials
/**           -> denyAll
```

Spring Security WebFlux supports multiple `SecurityWebFilterChain` beans using `@Order` and `securityMatcher(...)`. Each request selects the **first chain matching its matcher**; an authentication failure **does not cause Spring to fall through to the next chain**. Put a catch-all `denyAll` last rather than defaulting to `permitAll`.

The main lab below uses **one chain**, followed by a split-chain variant.

## 5. Java 17+ Project Supporting Basic, Bearer JWT, and Custom ApiKey

The example has five classes:

```text
src/main/java/com/example/multiauth/
  MultiAuthApplication.java
  ApiKeyAuthenticationToken.java
  ApiKeyAuthenticationManager.java
  MultiAuthSecurityConfig.java
  ReadController.java
src/main/resources/
  application.yml
src/test/java/com/example/multiauth/
  MultiAuthHttpTest.java
```

These files depend on Spring Boot/WebFlux/Security, so they cannot be compiled with bare `javac` without a classpath. To test JWT offline, the test injects a fake decoder **only in the test source set**. Production must use a real JWT decoder with a trusted IdP/JWKS, issuer, expiry, and audience validation.

### 5.1 build.gradle Dependencies

Generate a Spring Initializr project with Spring Boot 3.x, Java 17+, Gradle, Reactive Web, Security, and OAuth2 Resource Server. In `build.gradle` with the Spring Boot plugin and dependency management already present, add:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
tasks.named('test') {
    useJUnitPlatform()
}
```

Do not add `spring-boot-starter-web` if the app must run on WebFlux, because when both MVC and WebFlux are on the classpath, Spring Boot defaults to MVC.

### 5.2 application.yml

`src/main/resources/application.yml`:

```yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
          jwk-set-uri: https://idp.example.test/issuer/jwks

app:
  security:
    api-key: ${DEMO_API_KEY}
```

- `issuer-uri` is the trusted value of the `iss` claim; `jwk-set-uri` points to the signature verification key set.
- When both issuer and JWKS URI are configured, Spring Security continues to validate the issuer rather than skipping issuer checks.
- Production APIs must also validate `aud`, `exp`, `nbf`, allowed algorithms, and JWK rotation per the IdP.
- `example.test` is an illustrative domain with no live service; replace it with your registered IdP for real integration.
- `DEMO_API_KEY` comes from the environment or a secrets manager; **never commit production keys to YAML/repo**. This single-key in-RAM digest example is for illustration, not a production key registry architecture.

### 5.3 MultiAuthApplication.java

`src/main/java/com/example/multiauth/MultiAuthApplication.java`:

```java
package com.example.multiauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MultiAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(MultiAuthApplication.class, args);
    }
}
```

### 5.4 ApiKeyAuthenticationToken.java

A custom Authentication must separate **unauthenticated** from **authenticated**. Never construct a principal with authorities from a request header before verifying the key.

`src/main/java/com/example/multiauth/ApiKeyAuthenticationToken.java`:

```java
package com.example.multiauth;

import java.util.Collection;
import java.util.List;

import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;

public final class ApiKeyAuthenticationToken
        extends AbstractAuthenticationToken {

    private final String principal;
    private String apiKey;

    private ApiKeyAuthenticationToken(
            String principal,
            String apiKey,
            Collection<? extends GrantedAuthority> authorities,
            boolean verified) {

        super(authorities);
        this.principal = principal;
        this.apiKey = apiKey;
        if (verified) {
            // Only trusted factory path should set this true.
            super.setAuthenticated(true);
        }
    }

    public static ApiKeyAuthenticationToken unauthenticated(String key) {
        return new ApiKeyAuthenticationToken(
            "unverified", key, List.of(), false);
    }

    public static ApiKeyAuthenticationToken verified(
            String principal,
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
        return apiKey;
    }

    @Override
    public void eraseCredentials() {
        super.eraseCredentials();
        apiKey = null;
    }

    @Override
    public void setAuthenticated(boolean authenticated) {
        if (authenticated) {
            throw new IllegalArgumentException(
                "Cannot mark an unverified API key as authenticated");
        }
        super.setAuthenticated(false);
    }

    @Override
    public String toString() {
        return "ApiKeyAuthenticationToken[credentials=REDACTED]";
    }
}
```

**Explanation:**

1. `unauthenticated(key)` is merely an attempt, with no authorities.
2. `verified(...)` is called only **after the manager verifies the key**, returning a backend-determined principal and keeping no raw key inside the authenticated object.
3. Overriding the setter prevents normal callers from invoking `setAuthenticated(true)` on an attempt.
4. `toString()` never prints the key; `eraseCredentials()` clears the key reference from the object.
5. A public factory keeps the demo easy to follow, whereas production should **restrict trusted token creation** inside the security module (package-private or internal builder) and forbid business code from taking client-supplied principals/authorities and calling `verified`.

### 5.5 ApiKeyAuthenticationManager.java

This manager handles only `ApiKeyAuthenticationToken`, not Basic's `UsernamePasswordAuthenticationToken` or OAuth2's `BearerTokenAuthenticationToken`.

`src/main/java/com/example/multiauth/ApiKeyAuthenticationManager.java`:

```java
package com.example.multiauth;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.List;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import reactor.core.publisher.Mono;

public final class ApiKeyAuthenticationManager
        implements ReactiveAuthenticationManager {

    private final byte[] expectedDigest;

    public ApiKeyAuthenticationManager(String serverSecret) {
        if (serverSecret == null || serverSecret.length() < 32) {
            throw new IllegalArgumentException(
                "Demo API key must be a high-entropy secret");
        }
        this.expectedDigest = sha256(serverSecret);
    }

    @Override
    public Mono<Authentication> authenticate(Authentication input) {
        if (!(input instanceof ApiKeyAuthenticationToken token)) {
            // Unsupported Authentication type, not invalid API key.
            return Mono.empty();
        }

        return Mono.defer(() -> {
            Object supplied = token.getCredentials();
            if (!(supplied instanceof String raw)
                    || raw.isBlank()
                    || raw.length() > 256) {
                return Mono.error(
                    new BadCredentialsException("Invalid API key"));
            }

            boolean matches = MessageDigest.isEqual(
                expectedDigest, sha256(raw));

            if (!matches) {
                return Mono.error(
                    new BadCredentialsException("Invalid API key"));
            }

            return Mono.just((Authentication)
                ApiKeyAuthenticationToken.verified(
                    "partner-integration",
                    List.of(new SimpleGrantedAuthority(
                        "ROLE_PARTNER_READ"))
                )
            );
        });
    }

    private static byte[] sha256(String input) {
        try {
            return MessageDigest.getInstance("SHA-256")
                .digest(input.getBytes(StandardCharsets.UTF_8));
        }
        catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }
}
```

**Security analysis:**

- If the manager does not support the Authentication type, `Mono.empty()` is appropriate.
- If the attempt is ApiKey and the raw key is missing/wrong, the manager **emits `BadCredentialsException`** → HTTP 401.
- `MessageDigest.isEqual` compares digests in a way that reduces comparison timing leakage, though it does not replace secret protection, rate limiting, or key entropy.
- `ROLE_PARTNER_READ` is assigned solely by the backend; a client cannot send `X-Role: ADMIN` to become admin.
- API keys must be **random with high entropy**; never use short passwords thinking SHA-256 prevents offline guessing.
- Production typically stores **key hashes/HMACs**, key IDs, key status, expiry, rotation/overlap, customer/tenant mappings, and quotas in securely managed storage. The sample uses one env key for learning simplicity.
- When checking keys against a database or KMS, use a reactive client (Redis/R2DBC or async APIs), never `block()` on the Netty event loop.
- **Do not register this manager as a global `@Bean ReactiveAuthenticationManager`** in the demo: Basic needs its own password-verifying provider/manager; instantiate the custom manager inside the custom filter.

## 6. MultiAuthSecurityConfig.java: Combining Three Mechanisms

`src/main/java/com/example/multiauth/MultiAuthSecurityConfig.java`:

```java
package com.example.multiauth;

import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.AuthenticationWebFilter;
import org.springframework.security.web.server.authentication.HttpStatusServerEntryPoint;
import org.springframework.security.web.server.authentication.ServerAuthenticationEntryPointFailureHandler;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.web.server.WebFilter;

import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class MultiAuthSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        var reader = User.withUsername("reader")
            .password(encoder.encode("reader-demo-password"))
            .roles("BASIC_READ")
            .build();

        var admin = User.withUsername("administrator")
            .password(encoder.encode("admin-demo-password"))
            .roles("BASIC_READ", "ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            @Value("${app.security.api-key}") String apiKeySecret) {

        // Do NOT register the custom manager as the global Basic manager.
        var apiKeyManager = new ApiKeyAuthenticationManager(apiKeySecret);
        var apiKeyFilter = buildApiKeyFilter(apiKeyManager);

        return http
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance()
            )
            .addFilterAt(
                rejectAmbiguousAuthorizationHeaders(),
                SecurityWebFiltersOrder.FIRST
            )
            .addFilterAt(
                apiKeyFilter,
                SecurityWebFiltersOrder.AUTHENTICATION
            )
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/public/health").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/read")
                    .hasAnyAuthority(
                        "ROLE_BASIC_READ",
                        "ROLE_PARTNER_READ",
                        "SCOPE_messages.read"
                    )
                .pathMatchers(HttpMethod.GET, "/api/admin")
                    .hasAnyAuthority("ROLE_ADMIN", "SCOPE_api.admin")
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }

    private AuthenticationWebFilter buildApiKeyFilter(
            ApiKeyAuthenticationManager manager) {

        var filter = new AuthenticationWebFilter(manager);

        filter.setServerAuthenticationConverter(exchange -> {
            String header = exchange.getRequest().getHeaders()
                .getFirst(HttpHeaders.AUTHORIZATION);

            // Only the ApiKey scheme belongs to this converter.
            if (header == null ||
                    !header.regionMatches(true, 0, "ApiKey", 0, 6)) {
                return Mono.empty();
            }

            // Scheme recognized but value malformed: fail closed.
            if (!header.regionMatches(true, 0, "ApiKey ", 0, 7)
                    || header.length() <= 7
                    || header.length() > 263) {
                return Mono.error(new BadCredentialsException(
                    "Malformed API key"));
            }

            String key = header.substring(7);
            if (key.isBlank() || key.contains(" ")
                    || key.contains("\t")
                    || !key.equals(key.strip())) {
                return Mono.error(new BadCredentialsException(
                    "Malformed API key"));
            }

            return Mono.just(
                ApiKeyAuthenticationToken.unauthenticated(key)
            );
        });

        filter.setAuthenticationFailureHandler(
            new ServerAuthenticationEntryPointFailureHandler(
                new HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED)
            )
        );
        filter.setSecurityContextRepository(
            NoOpServerSecurityContextRepository.getInstance()
        );

        return filter;
    }

    private WebFilter rejectAmbiguousAuthorizationHeaders() {
        return (exchange, chain) -> {
            List<String> headers = exchange.getRequest().getHeaders()
                .getOrEmpty(HttpHeaders.AUTHORIZATION);

            // Demo policy: exactly one Authorization value at most.
            if (headers.size() > 1 ||
                    (headers.size() == 1
                        && headers.get(0) != null
                        && headers.get(0).contains(","))) {
                exchange.getResponse()
                    .setStatusCode(HttpStatus.BAD_REQUEST);
                return exchange.getResponse().setComplete();
            }
            return chain.filter(exchange);
        };
    }
}
```

### 6.1 How Coordination Works in Practice

- `Basic ...` request → ApiKey converter returns `Mono.empty()`; Basic auth filter checks username/password via `MapReactiveUserDetailsService` and password encoder.
- `Bearer ...` request → ApiKey converter returns `Mono.empty()`; JWT Resource Server filter uses `ReactiveJwtDecoder` from Boot config.
- `ApiKey ...` request → Basic/Bearer ignore this scheme; custom converter builds an unauthenticated ApiKey token and the custom manager verifies the key.
- `ApiKey` missing value → custom converter emits an exception, with no fallback.
- Request with two Authorization header fields → guard rejects before authentication.
- If no credential is sent to a protected endpoint, authorization returns 401 via the active entry point.
- The `hasAnyAuthority` rule checks authorities **granted separately by each mechanism**. Nowhere can the caller pick their own role or scope.

### 6.2 Why Use SecurityWebFiltersOrder.AUTHENTICATION?

`AuthenticationWebFilter` needs to run after request/security context setup and **before authorization**. `addFilterAt(..., SecurityWebFiltersOrder.AUTHENTICATION)` is the proper slot for custom authentication in the WebFlux chain.

Filters sharing the same authentication order must not be used as a strong-vs-weak ordering rule. This example routes by **disjoint header schemes**: the custom filter handles only `ApiKey`, while built-ins handle `Basic` and `Bearer`. Thus the outcome does not depend on "which mechanism tries first".

`SecurityWebFiltersOrder.FIRST` on the guard rejects conflicting Authorization headers early. In production, ingress/proxies must also inspect multiple Authorization header values and coalescing behavior across HTTP/1.1 and HTTP/2.

### 6.3 Stateless Authentication

`NoOpServerSecurityContextRepository` avoids saving `SecurityContext` between requests. An authenticated `Authentication` is placed into the **current request's Reactor Context**, not reused across requests like a login session. This is the right choice for APIs using per-request credentials.

Browsers may automatically resend HTTP Basic credentials from their credential cache; if mutation endpoints exist, **CSRF policy still needs threat modeling**. A sessionless API does not automatically mean zero CSRF risk.

### 6.4 Confusing a Manager Bean with a Local Manager

If you write:

```java
@Bean
ReactiveAuthenticationManager customManager(...) {
    return new ApiKeyAuthenticationManager(...);
}
```

and Spring Security picks it up as the **default authentication manager**, HTTP Basic may no longer handle `UsernamePasswordAuthenticationToken` as intended. In the main example, we **do not** register the custom manager globally; the instance is passed directly into `new AuthenticationWebFilter(manager)`.

If production requires multiple manager beans, configure explicit `@Qualifier`s and ensure **each filter uses the exact intended manager** rather than relying on ambiguous auto-wiring.

## 7. ReadController.java

`src/main/java/com/example/multiauth/ReadController.java`:

```java
package com.example.multiauth;

import java.security.Principal;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ReadController {

    public record Result(String principal, String operation) {}

    @GetMapping(
        value = "/public/health",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> health() {
        return Mono.just("ok");
    }

    @GetMapping(
        value = "/api/read",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<Result> read(Principal principal) {
        return Mono.just(new Result(principal.getName(), "read"));
    }

    @GetMapping(
        value = "/api/admin",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<Result> admin(Principal principal) {
        return Mono.just(new Result(principal.getName(), "admin"));
    }
}
```

`Principal` is populated from Spring Security's `SecurityContext`, **never from an `X-User` HTTP header**. For Basic, the name is the authenticated username; for JWT, typically the JWT `sub`; for the demo ApiKey, the name assigned by the custom manager (`partner-integration`). Never confuse a principal name with proof of ownership across every resource or tenant.

## 8. WebTestClient Testing: 15 Test Cases

Create test source `src/test/java/com/example/multiauth/MultiAuthHttpTest.java`.

The test suite uses `WebTestClient.bindToApplicationContext(...)` + `springSecurity()`. To avoid needing a real IdP/JWKS, a `@TestConfiguration` provides a fake `ReactiveJwtDecoder` **strictly in the test context**. The fake decoder lets us test Bearer filter routing and scope authorities offline, **but does not verify JWT cryptography**; a later subsection covers real JWT testing.

### 8.1 MultiAuthHttpTest.java

```java
package com.example.multiauth;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

import java.time.Instant;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK,
    properties = {
        "app.security.api-key=local-test-api-key-0123456789-ABCDEFabcdef",
        "spring.security.oauth2.resourceserver.jwt.issuer-uri=https://idp.example.test/issuer",
        "spring.security.oauth2.resourceserver.jwt.jwk-set-uri=https://idp.example.test/issuer/jwks"
    }
)
@Import(MultiAuthHttpTest.TestJwtDecoder.class)
class MultiAuthHttpTest {

    private static final String API_KEY =
        "local-test-api-key-0123456789-ABCDEFabcdef";

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @TestConfiguration(proxyBeanMethods = false)
    static class TestJwtDecoder {

        @Bean
        @Primary
        ReactiveJwtDecoder fakeDecoder() {
            return raw -> {
                String scope;
                switch (raw) {
                    case "jwt-reader" -> scope = "messages.read";
                    case "jwt-admin" -> scope = "api.admin";
                    case "jwt-other" -> scope = "profile.read";
                    default -> {
                        return Mono.error(
                            new BadJwtException("Invalid test JWT"));
                    }
                }

                Instant now = Instant.now();
                Jwt jwt = Jwt.withTokenValue(raw)
                    .header("alg", "RS256")
                    .claim("sub", "jwt-alice")
                    .claim("scope", scope)
                    .issuedAt(now.minusSeconds(30))
                    .expiresAt(now.plusSeconds(1800))
                    .build();

                return Mono.just(jwt);
            };
        }
    }

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void publicHealthNeedsNoCredentials() {
        client.get().uri("/public/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("ok");
    }

    @Test
    void noCredentialsCannotRead() {
        client.get().uri("/api/read")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void basicReaderCanRead() {
        client.get().uri("/api/read")
            .headers(h -> h.setBasicAuth(
                "reader", "reader-demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.principal").isEqualTo("reader");
    }

    @Test
    void wrongBasicPasswordReturns401() {
        client.get().uri("/api/read")
            .headers(h -> h.setBasicAuth("reader", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void readerCannotAdmin() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth(
                "reader", "reader-demo-password"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void administratorCanAdmin() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth(
                "administrator", "admin-demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.operation").isEqualTo("admin");
    }

    @Test
    void correctApiKeyCanRead() {
        client.get().uri("/api/read")
            .header(HttpHeaders.AUTHORIZATION, "ApiKey " + API_KEY)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.principal").isEqualTo("partner-integration");
    }

    @Test
    void wrongApiKeyFailsWithoutFallback() {
        client.get().uri("/api/read")
            .header(HttpHeaders.AUTHORIZATION,
                "ApiKey wrong-example-secret")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void malformedApiKeyFails() {
        client.get().uri("/api/read")
            .header(HttpHeaders.AUTHORIZATION, "ApiKey")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void apiKeyCannotAdmin() {
        client.get().uri("/api/admin")
            .header(HttpHeaders.AUTHORIZATION, "ApiKey " + API_KEY)
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void bearerWithReadScopeCanRead() {
        client.get().uri("/api/read")
            .header(HttpHeaders.AUTHORIZATION, "Bearer jwt-reader")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.principal").isEqualTo("jwt-alice");
    }

    @Test
    void bearerMissingScopeGets403() {
        client.get().uri("/api/read")
            .header(HttpHeaders.AUTHORIZATION, "Bearer jwt-other")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void invalidBearerGets401() {
        client.get().uri("/api/read")
            .header(HttpHeaders.AUTHORIZATION, "Bearer invalid-test-jwt")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void bearerWithAdminScopeCanAdmin() {
        client.get().uri("/api/admin")
            .header(HttpHeaders.AUTHORIZATION, "Bearer jwt-admin")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.operation").isEqualTo("admin");
    }

    @Test
    void duplicateAuthorizationHeadersAreRejected() {
        client.get().uri("/api/read")
            .header(HttpHeaders.AUTHORIZATION,
                "Bearer jwt-reader",
                "ApiKey " + API_KEY)
            .exchange()
            .expectStatus().isBadRequest();
    }
}
```

Run:

```bash
./gradlew test --tests '*MultiAuthHttpTest'
```

Windows:

```powershell
.\gradlew.bat test --tests '*MultiAuthHttpTest'
```

These are **15 test cases and their expected HTTP assertions**, not Gradle stdout captured during authoring. The example code has been reviewed against Spring Security 6.5 APIs, yet you must run the tests with your actual Boot/dependency versions to confirm.

### 8.2 Why Do 401 and 403 Differ?

- Wrong Basic/password → **authentication failure**, 401.
- Malformed/invalid JWT → **authentication failure**, 401.
- Wrong API key → **authentication failure**, 401.
- Valid token/key/password but route requires an ungranted authority → **authorization denial**, typically 403.
- Multiple `Authorization` header values → conflicting request; the demo guard returns **400** before authentication.
- CORS preflight may need separate handling; it never turns an invalid credential into a valid one.

In Spring Security, the actual status also depends on entry points, chains, and exception handling, especially for anonymous requests. The tests illustrate intentional behavior without requiring every app to emit the exact same `WWW-Authenticate` challenge.

### 8.3 Why Does the Fake ReactiveJwtDecoder Exist Only in Tests?

The fake decoder accepts the string `jwt-reader` even though it is not a signed JWT. It helps test filter routing and scope authorities offline, **but does not prove production JWT security**.

Staging integration tests need a **real decoder** and signed JWTs verifying:
- valid/invalid JWS signatures;
- trusted issuer `iss`;
- JWT `exp` and `nbf`;
- matching/mismatching resource audience `aud`;
- trusted `alg`/key IDs;
- key rotation/JWKS caching;
- never accepting a token from issuer A as issuer B;
- accurate scope/role mapping.

Never copy `fakeDecoder()` from tests into main code or enable a `ReactiveJwtDecoder` that unconditionally returns `Mono.just(...)` in production.

## 9. Manual Execution via curl

Run the app on localhost with the demo key:

```bash
export DEMO_API_KEY="local-test-api-key-0123456789-ABCDEFabcdef"
./gradlew bootRun
```

PowerShell:

```powershell
$env:DEMO_API_KEY = "local-test-api-key-0123456789-ABCDEFabcdef"
.\gradlew.bat bootRun
```

### 9.1 HTTP Basic

```bash
curl -i -u reader http://localhost:8080/api/read
```

`curl` prompts for a password; enter `reader-demo-password`. Expect 200 with `"principal":"reader"`. Calling `/api/admin` as `reader` returns 403; using `administrator` with demo password `admin-demo-password` returns 200.

**Never send Basic passwords over plain HTTP on real networks.** Localhost commands are strictly for learning; in production, HTTPS/TLS with proper trust boundaries is mandatory.

### 9.2 Custom ApiKey

```bash
curl -i http://localhost:8080/api/read \
  -H "Authorization: ApiKey local-test-api-key-0123456789-ABCDEFabcdef"
```

Expect 200 with `partner-integration`. Changing one character produces 401; calling `/api/admin` with the valid key returns 403 because it lacks `ROLE_ADMIN`.

Never pass production API keys in commands exposed to shell history, process inspection, tickets, or logs. Use your environment's proper secret injection mechanism.

### 9.3 Bearer JWT

```bash
curl -i http://localhost:8080/api/read \
  -H "Authorization: Bearer <SIGNED_ACCESS_TOKEN_FROM_IDP>"
```

Succeeds only with a real configured IdP/JWKS and a token carrying the right issuer, audience, signature, and scope. The `jwt-reader` string from tests is not a real token; a production server will reject it.

## 10. If You Only Need Custom + HTTP Basic

If the system does not yet need Bearer:
- Remove the OAuth2 Resource Server starter if unused elsewhere.
- Remove `spring.security.oauth2.resourceserver.jwt.*`.
- Remove `.oauth2ResourceServer(...jwt(...))`.
- Keep `httpBasic(Customizer.withDefaults())`, the custom `AuthenticationWebFilter`, and the API-key manager.
- Use authority rules containing only `ROLE_BASIC_READ` or `ROLE_PARTNER_READ`.

When a Bearer token arrives at a system supporting only Basic+ApiKey, no filter verifies it and the protected API rejects it. **Never try to treat a Bearer token as an API key**.

### 10.1 If Your Company Uses an X-API-Key Header

You can swap the custom converter to read the `X-API-Key` header. In that case, a request might send both `Authorization: Bearer ...` and `X-API-Key: ...` simultaneously, creating ambiguous authentication. Reject immediately when both appear rather than picking "whichever valid credential works".

Pseudocode:

```text
if X-API-Key absent:
    custom converter -> Mono.empty()
else if Authorization present:
    reject mixed credentials early -> 400/401
else if X-API-Key malformed:
    custom converter -> AuthenticationException
else:
    custom converter -> unauthenticated ApiKeyAuthenticationToken
    manager -> verify -> authenticated principal/authorities
```

With a custom header, the guard must run **before all authentication filters**, never relying on ordering between the Bearer filter and a same-order custom filter. Rate limiting, storage, and rotation for API keys remain just as necessary as with a custom `Authorization` scheme.

## 11. If You Need Custom + Opaque Bearer Instead of JWT

If the Authorization Server issues **opaque access tokens**, replace JWT Resource Server with introspection:

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults())
)
```

and properties:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.test/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

This is an **alternative variant replacing JWT**, not instructions to turn on both JWT and opaque on the same Bearer resolver. `ReactiveOpaqueTokenIntrospector` calls the RFC 7662 introspection endpoint to verify token status, and scopes can map to `SCOPE_...`. Any `active:false` response must fail authentication; never fall back to ApiKey or Basic.

**Secret protection:** `client-id`/`client-secret` here are credentials for the Resource Server to query the IdP, **not** the caller's Bearer token. Use HTTPS, a secret manager, bounded timeouts/retries, and never fail open on IdP timeouts.

## 12. Splitting Multiple SecurityWebFilterChains by Path

If Basic is for internal use and Bearer is for public APIs, it is cleaner to split chains:

```java
@Bean
@Order(1)
SecurityWebFilterChain publicApi(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**"))
        .authorizeExchange(ex -> ex
            .anyExchange().hasAuthority("SCOPE_messages.read"))
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
```

This is a **bean snippet** requiring imports for `Bean`, `Order`, `SecurityWebFilterChain`, `PathPatternParserServerWebExchangeMatcher`, and `Customizer`. Add another chain for `/internal/**` using Basic, another for `/partner/**` using custom API keys, and finally a catch-all `denyAll`.

**Remember:** `securityMatcher` selects the chain, whereas `authorizeExchange` enforces permissions inside the chain. Spring Security runs only the **first matching chain**; an invalid Bearer token in the `/api/**` chain **does not** cause the request to continue to the Basic chain. That property prevents auth downgrades.

### 12.1 Architecture Comparison

| Need | Recommendation | Note |
| --- | --- | --- |
| Single endpoint migrating Basic → Bearer | Single chain with disjoint converters | Test all positive/negative/scheme conflicts |
| Public Bearer API, internal Basic admin | Multiple chains by URL | Explicit matchers/order/catch-all |
| Partner API key read-only | Separate chain or shared chain with scoped authority | Quotas/key rotation + 403 for admin |
| Multiple issuers/tenants | Trusted routing, resolvers, or chains | Never pick issuer from untrusted token payload |
| Browser session/OIDC | Chain with proper session/CSRF | Never carelessly merge with stateless bearer |
| Uncertain whether token is JWT or opaque | Pick one fitting validation strategy | Never skip JWT validation when token is invalid |

## 13. Common Mistakes and Risks

### 13.1 Turning Bad Credentials into Mono.empty

Wrong:

```java
if (badKey) {
    return Mono.empty();
}
```

Right:

```java
if (badKey) {
    return Mono.error(new BadCredentialsException("Invalid API key"));
}
```

A recognized but invalid credential must produce an authentication failure, not "no credential seen".

### 13.2 Using One Manager for Every Credential

Do not lump Basic username/password, JWT access tokens, and API keys into a single string with ad-hoc `if`/`else` logic. Keep them separate:
- HTTP Basic uses user details/password encoders.
- Bearer uses Resource Server JWT decoders or opaque introspection.
- ApiKey uses a custom manager verifying secrets.
- Separate authority and domain authorization rules.

### 13.3 Trusting Roles from Requests

Never create an `ADMIN` principal because a client sent `X-Role: ADMIN` or `?role=admin`. A custom manager must assign privileges from verified server-side records. JWT authorities must come from **verified claims**, never from Base64 payloads decoded without signature verification.

### 13.4 Storing Keys in Plaintext Without Rotation

The demo uses a single env key hashed in RAM. Production needs a key registry, key IDs, hashed storage, expiry/revocation, high entropy, rate/usage limits, and zero-downtime rotation across clients. `MessageDigest.isEqual` helps compare digests, yet it **does not** save a weak key or stop brute-force attacks.

### 13.5 Authorization Header Ambiguity

Two `Authorization` values can be coalesced by a gateway or handled differently across HTTP/1.1 and HTTP/2. Validate at both ingress and app layers, and test raw requests through your actual proxy. The demo guard returns 400 on multiple values or commas within a value, tailored to these three schemes rather than claiming every HTTP auth scheme forbids commas.

### 13.6 HTTP Basic/TLS

`Basic <base64>` does not encrypt usernames or passwords; use it only over properly validated HTTPS, avoid logging raw `Authorization`, and enforce rate limits and password policies. Browsers may resend Basic credentials automatically, so evaluate CSRF when mutation endpoints exist.

### 13.7 Incomplete JWT Validation

Never use the test's fake `ReactiveJwtDecoder` in production. Validate trusted issuer, JWKS/signature, allowed algorithms, expiry, audience, scopes, key rotation, and HTTPS. If the Resource Server receives a JWT minted for another API's audience, never allow access "just because the signature is valid".

### 13.8 Successful Authentication Is Not Universal Authorization

A key carrying `ROLE_PARTNER_READ` should only read permitted routes. Multi-tenant data still requires specific resource/owner/tenant checks, not just a broad `hasAuthority`.

### 13.9 CSRF, CORS, and HTTPS Are Distinct Layers

- **CORS:** controls whether a browser can send/read cross-origin requests; preflights normally carry no credentials and must be handled early.
- **CSRF:** browser requests with side effects can exploit ambient credentials, requiring policies matched to client/route types.
- **TLS:** protects credentials in transit.
- **Authentication:** verifies Basic/Bearer/ApiKey.
- **Authorization:** enforces scope/role permissions and data ownership.

Never fix a 401 on `OPTIONS` by adding `anyExchange().permitAll()`; never disable CSRF app-wide just because a POST test returned 403.

## 14. Troubleshooting Table

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| Valid Basic gets 401 after adding custom manager | Spring picked custom manager as default | Do not register globally; attach directly to custom filter |
| Wrong ApiKey still returns 200 | Converter returned empty or endpoint is `permitAll` | Emit `BadCredentialsException`; add negative tests |
| ApiKey missing value gives no error | Malformed scheme skipped | Distinguish recognized scheme vs unsupported |
| Valid Bearer JWT gets 401 | Wrong issuer/audience/expiry/signature/JWKS | Test real decoder and IdP |
| Bearer lacking scope still gets 200 | Rule only used `authenticated` | Use `hasAuthority("SCOPE_...")` |
| ApiKey can call admin | Manager granted overly broad authority | Scope/key registry with least privilege |
| 2 Authorization headers behave inconsistently | Gateway/app header parsing differs | Reject duplicates at edge/app |
| Custom filter does not run | Not added via `addFilterAt` in matching chain | Check `SecurityWebFiltersOrder` and matchers |
| Auth fails then falls back to Basic | `onErrorResume` swallowed `BadCredentials` | Never fall back on error |
| Browser CORS fails even though curl returns 200 | CORS is separate from authentication | Check `OPTIONS`/`Access-Control-*` |
| Browser POST returns 403 | CSRF or role denial | Classify the security failure accurately |
| Mock JWT tests pass, staging gets 401 | Fake decoder bypassed cryptography | Integration test with real IdP/JWKS |
| API key leaked in logs | Logged raw `Authorization` | Redact; log only key ID after auth |
| Leaked key stays usable for long | Missing revocation/rotation | Versioned keys/TTL/incident runbook |
| High latency looking up keys | Blocking DB on Netty thread | Reactive DB client, timeouts/bulkheads |
| Unmatched chain makes route public | Catch-all chain used `permitAll` | Catch-all `denyAll` |
| HTTP Basic works over plain HTTP | Credentials vulnerable to eavesdropping | Enforce HTTPS at ingress and internally |
| Resource Server returns 503 when IdP is down | Introspection/JWKS dependency failed | Fail closed, SLO/timeouts; never turn anonymous into trusted |

## 15. Review Questions

**1. Does `Mono.empty()` from the custom converter mean the key is wrong?** No. It means the converter **did not recognize its credential** (e.g., Basic/Bearer). A wrong key must emit `AuthenticationException`.

**2. Should the Basic manager handle `ApiKeyAuthenticationToken`?** Not in this demo. Basic verifies passwords against user details; the API key has its own manager.

**3. When should 401 be returned?** When authentication fails or is absent: missing/wrong Basic, invalid Bearer, wrong/malformed ApiKey. Entry points may vary, but must fail closed.

**4. When should 403 be returned?** When the principal is authenticated yet lacks the required authority/role/scope or is denied by domain policy.

**5. Is a Bearer token that looks like a JWT trustworthy enough?** No. Signature, issuer, audience, expiry, and claims must be verified by the Resource Server.

**6. Why not put an API key inside Bearer and compare keys only if JWT verification fails?** It conflates OAuth2 Bearer semantics with custom keys, risking downgrades and signature-validation bypasses.

**7. Why shouldn't a custom manager be registered as the default `ReactiveAuthenticationManager` bean?** It can cause the Basic filter to use a manager that does not support username/password tokens.

**8. Why use an unauthenticated `ApiKeyAuthenticationToken`?** Because credentials taken from HTTP clients are untrusted. Only after manager verification are a trusted token and authorities created.

**9. Does a valid API key automatically receive `ROLE_ADMIN`?** No. The demo grants only `ROLE_PARTNER_READ`, so admin endpoints still return 403.

**10. Why check for duplicate Authorization headers?** Prevents parsers and gateways from choosing different credentials, avoiding confused-deputy bugs or auth bypasses.

**11. How do one chain and multiple chains differ?** One chain can support multiple schemes on the same path; multiple chains select by `securityMatcher` and `@Order`, separating trust boundaries.

**12. Can `X-API-Key` coexist with `Authorization: Basic`?** At the HTTP level yes, but security policy should reject mixed credentials unless explicitly designed; the guard must run before both.

**13. Does HTTP Basic Base64 provide encryption?** No. TLS and password protection are required.

**14. Why does `SecurityWebFiltersOrder.AUTHENTICATION` matter?** Places the custom filter in the authentication phase, before authorization. Never rely on it to guarantee ordering among same-order filters.

**15. Are `mockJwt()` or a fake JWT decoder enough to test real cryptography?** No. They test policy/routing; a real decoder and signed tokens are needed in integration tests.

## 16. Production Checklist

- [ ] Clearly define allowed schemes per path/client rather than accepting arbitrary schemes.
- [ ] Custom converter returns `Mono.empty` on non-matching scheme and errors when a recognized scheme has malformed credentials.
- [ ] Custom manager accepts only its custom Authentication type without breaking Basic/JWT managers.
- [ ] Unauthenticated tokens carry no authorities; authenticated tokens are built from server-side verification.
- [ ] Custom `AuthenticationWebFilter` sits inside `SecurityWebFilterChain` at the authentication phase.
- [ ] Never rely on filter ordering as a fallback or strong-vs-weak auth selector.
- [ ] Reject mixed/duplicate `Authorization` credentials and test through real gateways.
- [ ] Basic uses a password encoder/user service; no real passwords stored in source.
- [ ] Bearer uses JWT signature + issuer/audience/expiry or opaque introspection; never parse unverified payloads.
- [ ] API keys have high entropy, hashed/secret storage, versioning, revocation/rotation, and per-client quotas.
- [ ] Each mechanism grants least-privilege authorities; endpoints enforce clear role/scope/domain rules.
- [ ] Positive/negative tests cover Basic, Bearer, and ApiKey, including 401/403 and duplicate headers.
- [ ] Integration JWT verification tests go beyond the fake decoder; IdP/JWKS/clock/key rotation are tested.
- [ ] HTTPS/TLS enforced, credentials never logged, and rate limits applied.
- [ ] CORS preflight is not blocked by auth; CSRF policies for browser mutations are evaluated.
- [ ] With multiple chains, `@Order`/`securityMatcher` are accurate and end with a catch-all `denyAll`.
- [ ] Never call `block()` in the reactive authentication path when looking up secrets from DB/KMS.
- [ ] Sanitized metrics track auth scheme, success/failure, latency, suspicious attempts, and incident response.

## 17. Summary

**Combining custom authentication with HTTP Basic or Bearer tokens** in WebFlux does not mean writing a single authentication manager that accepts every secret string and tries providers until one passes. Let Spring Security handle the standard mechanisms:
- `httpBasic()` verifies Basic username/password via a password encoder and user details;
- `oauth2ResourceServer().jwt()` or `opaqueToken()` verifies Bearer access tokens per trust policy;
- `AuthenticationWebFilter + ServerAuthenticationConverter + ReactiveAuthenticationManager` handles an explicitly recognized custom scheme.

**Three key takeaways:** (1) non-matching scheme → `Mono.empty`; matching scheme with invalid credential → `AuthenticationException`, (2) successful authentication is not enough—pair it with role/scope/tenant/resource authorization, and (3) never mix credentials or fall back from a strong mechanism to a weak one. When client groups have different trust boundaries, splitting `SecurityWebFilterChain`s by URL is easier to audit.

### Official References

- [Spring Security 6.5 — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security 6.5 — Reactive HTTP Basic](https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/passwords/basic.html)
- [Spring Security 6.5 — JWT Resource Server](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html)
- [Spring Security 6.5 — Opaque Resource Server](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security 6.5 — AuthenticationWebFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html)
- [Spring Security 6.5 — SecurityWebFiltersOrder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/SecurityWebFiltersOrder.html)
- [Spring Security 6.5 — ServerAuthenticationConverter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationConverter.html)
- [Spring Security 6.5 — ReactiveAuthenticationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html)
- [Spring Security 6.5 — Reactive OAuth2 Tests](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700)
