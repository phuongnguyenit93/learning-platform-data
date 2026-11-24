# Implementing Custom API Keys with Key Rotation and Scoped Permissions in Spring Security Reactive

## 1. Problem Statement and Target Outcome

A partner needs to call a machine-to-machine orders API on a **Spring WebFlux + Spring Security Reactive** application. Each partner holds one or more API keys; each key is restricted to only the actions granted to it. The system must allow issuing a new key, migrating the client to the new key within a safe overlap window, and then revoking the old key **without interrupting the new key**. When a key leaks, administrators must revoke it quickly, audit who used which key, and prevent that key from exceeding its scope.

This lab builds a complete pipeline:

```text
Client -- HTTPS: X-API-Key --> API gateway / reverse proxy
    -> Spring Security Reactive SecurityWebFilterChain
    -> AuthenticationWebFilter
    -> ServerAuthenticationConverter (extracts exactly 1 key)
    -> ReactiveAuthenticationManager
    -> Reactive key repository / verifier + validity + status
    -> Authentication(principal, key-specific authorities)
    -> authorizeExchange (path + HTTP method + scope)
    -> tenant/resource authorization in business logic
    -> WebFlux handler
```

After this lesson, you should be able to:

1. Choose an **API key format with a public identifier and a high-entropy random secret**, displaying the secret only upon issuance.
2. Store a **digest/verifier** instead of the raw key; verify using constant-time digest comparison plus expiration and revocation checks.
3. Place the authentication result into the **Reactor Context** via Spring Security's standard mechanism rather than rolling a custom `ThreadLocal`.
4. Grant **per-key authorities**, enforce HTTP method, endpoint, and tenant checks, and distinguish 401 from 403.
5. Perform **short-lived two-key overlap rotation**, prove the new key works, revoke the old key, and verify 401.
6. Run automated tests, design a durable data model, and plan for multiple replicas, caching, auditing, and rate limiting.

An API key here represents the **calling application**, not automatically an authenticated end user. If two services can use OAuth2 Client Credentials, mTLS, or short-lived tokens on existing infrastructure, consider those managed protocols. When custom API key integration is required, design its lifecycle and access policies rigorously.

## 2. Security and Authorization Model

Suppose the API has two operations:

| HTTP | Path | Required authority | Data scope |
| --- | --- | --- | --- |
| `GET` | `/api/orders/{tenantId}` | `KEY_orders:read` | Only the tenant bound to the key |
| `POST` | `/api/orders/{tenantId}` | `KEY_orders:write` | Only the tenant bound to the key |
| Any other method/path | `/api/**` | No allow rule | Denied by default |

Distinguish three verification layers:

- **Authentication:** does the key exist, does the digest match, is it active, unexpired, and unrevoked? If not, return **401** without revealing which key IDs exist.
- **Functional authorization:** does the key have `orders:read` or `orders:write`? A valid key missing the authority typically returns **403**.
- **Data authorization:** a key issued for tenant A must not access tenant B, even with `orders:read`. In production, bind tenant/owner checks into queries and business transactions; URL checks alone cannot stop IDOR/BOLA.

**Privileges belong to each key, not inferred from the client.** A client holding a read key and a write key has two separate capabilities. Issuing a new key must never auto-expand scopes; the issuer can grant only approved scopes.

Never pass API keys in URLs/query strings (which leak into access logs, history, analytics, and `Referer`), shared request bodies, or browser cookies. Use a dedicated `X-API-Key` header over **mandatory HTTPS**, stripping or normalizing suspicious headers at the proxy. Never embed long-lived keys in frontend JavaScript, broadly distributed mobile apps, or public repositories; those environments cannot keep secrets safe like a trusted backend.

## 3. Designing the API Key Format and Storage

### 3.1. Public Identifier + High-Entropy Secret

An illustrative key format:

```text
ak1_<public-id-22-chars>.<secret-43-chars>
```

- `ak1_` is a version/prefix to identify the credential type and support future format migrations.
- `public-id` is 16 random bytes encoded as unpadded Base64URL (22 chars), stored for **indexed lookup**. The public ID is not a secret.
- `secret` is 32 bytes from `SecureRandom` encoded as unpadded Base64URL (43 chars): **256 bits of entropy**—never let users pick short or guessable keys.
- The entire string `ak1_<id>.<secret>` is a **bearer credential**: anyone possessing it can call the API within the key's scope until expiration or revocation.

Splitting on `.` is only to locate the public ID; the server still computes `SHA-256` over the **entire raw key string** and compares against the stored 32-byte digest. Use `MessageDigest.isEqual` for digest comparison instead of `String.equals`. SHA-256 fits here because the credential is randomly generated with 256 bits of entropy; **do not apply this fast hash formula to user-chosen passwords**. Passwords require suitable algorithms such as Argon2id/bcrypt/scrypt and corresponding policies.

Raw keys cannot be recovered from digests. After initial issuance, if a user loses a key, issue a **new** key rather than building a “view secret again” feature. For stricter threat models, use HMAC-SHA-256 with a secret pepper stored in an independent KMS/vault; in that case, plan pepper versioning and digest migration rather than committing the pepper to Git.

### 3.2. Record Fields to Persist

| Field | Meaning |
| --- | --- |
| `key_id` | Random public ID; exact lookup, auditing, and revocation |
| `client_id` | Identifier of the integration/service owning the key |
| `tenant_id` | Tenant identifier the key is permitted to access |
| `verifier_sha256` | 32-byte digest of the **full raw key** |
| `permissions` | Approved scope set for the key; e.g. `orders:read` |
| `not_before` | Key is invalid prior to this timestamp |
| `expires_at` | Key becomes invalid at and after this timestamp |
| `revoked_at` | Non-null indicates the key has been revoked |
| `created_at`, `last_used_at` | Lifecycle and security observability |
| `created_by`, `rotation_group` | Issuance audit and linkage between old and new keys |

**Invariant:** a revoked key must never be “re-enabled,” and you must never overwrite an old key's digest to rotate its secret. Every rotation must create a **new key ID and secret**, and maximum privileges must never exceed approved limits. Two keys may remain valid simultaneously during a controlled transition window.

## 4. Complete Java 17+ Example for the WebFlux Layer

This example intentionally uses `ConcurrentHashMap` as an in-memory key store so students can run tests without a database. It demonstrates authentication logic, per-key authorities, revocation, and rotation; **do not use this in-memory store directly in multi-replica production**, because keys are lost on restart and pods will not share state.

File `src/main/java/example/apikey/ApiKeySecurityConfig.java`:

```java
package example.apikey;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.Principal;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authentication.AuthenticationWebFilter;
import org.springframework.security.web.server.authentication.ServerAuthenticationEntryPointFailureHandler;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class ApiKeySecurityConfig {

    @Bean
    InMemoryApiKeyStore apiKeyStore() {
        return new InMemoryApiKeyStore(Clock.systemUTC());
    }

    @Bean
    @Order(0)
    SecurityWebFilterChain apiKeys(ServerHttpSecurity http,
                                  InMemoryApiKeyStore store) {

        ServerAuthenticationEntryPoint unauthorized = (exchange, error) -> {
            exchange.getResponse().setStatusCode(HttpStatus.UNAUTHORIZED);
            exchange.getResponse().getHeaders().set(
                    HttpHeaders.WWW_AUTHENTICATE, "ApiKey realm=\"orders\"");
            return exchange.getResponse().setComplete();
        };

        // Authenticate only unauthenticated candidate credentials.
        ReactiveAuthenticationManager manager = candidate -> {
            if (!(candidate instanceof UsernamePasswordAuthenticationToken)
                    || candidate.isAuthenticated()) {
                return Mono.empty();
            }
            Object credentials = candidate.getCredentials();
            if (!(credentials instanceof String raw)) {
                return Mono.error(new BadCredentialsException("Invalid API key"));
            }

            return store.findActive(raw)
                    .map(record -> {
                        ApiClient principal = new ApiClient(
                                record.clientId(),
                                record.tenantId(),
                                record.keyId());
                        var authorities = record.permissions().stream()
                                .map(permission ->
                                        new SimpleGrantedAuthority("KEY_" + permission))
                                .toList();

                        // 3-arg constructor = authenticated Authentication.
                        return (Authentication) new UsernamePasswordAuthenticationToken(
                                principal, null, authorities);
                    })
                    .switchIfEmpty(Mono.error(
                            new BadCredentialsException("Invalid API key")));
        };

        AuthenticationWebFilter filter = new AuthenticationWebFilter(manager);
        filter.setRequiresAuthenticationMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**"));

        filter.setServerAuthenticationConverter(exchange -> {
            List<String> headers = exchange.getRequest()
                    .getHeaders().getOrEmpty("X-API-Key");

            if (headers.isEmpty()) {
                return Mono.empty(); // let authorization entry point return 401
            }

            // Multiple values or abnormal length are treated as invalid.
            String raw = headers.size() == 1
                    && headers.get(0).length() <= 256
                    ? headers.get(0) : "";

            return Mono.just((Authentication)
                    new UsernamePasswordAuthenticationToken("api-key", raw));
        });

        // Every request must re-supply the key; do not store in WebSession.
        filter.setSecurityContextRepository(
                NoOpServerSecurityContextRepository.getInstance());
        filter.setAuthenticationFailureHandler(
                new ServerAuthenticationEntryPointFailureHandler(unauthorized));

        return http
                .securityMatcher(
                        new PathPatternParserServerWebExchangeMatcher("/api/**"))
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                .exceptionHandling(spec ->
                        spec.authenticationEntryPoint(unauthorized))
                // Applies only to pure header-key APIs that do not use
                // cookies/sessions as credentials for these routes.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .logout(ServerHttpSecurity.LogoutSpec::disable)
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("KEY_orders:read")
                        .pathMatchers(HttpMethod.POST, "/api/orders/**")
                            .hasAuthority("KEY_orders:write")
                        .anyExchange().denyAll())
                .addFilterAt(filter, SecurityWebFiltersOrder.AUTHENTICATION)
                .build();
    }

    // Safe demo fallback: deny all requests outside /api/**.
    // In apps with UI/OAuth2, replace with an appropriate dedicated chain.
    @Bean
    @Order(1)
    SecurityWebFilterChain denyUnknownRoutes(ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex.anyExchange().denyAll())
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }

    // Principal backed by the verified key record.
    public record ApiClient(
            String clientId, String tenantId, String keyId) implements Principal {
        @Override
        public String getName() {
            return clientId;
        }
    }

    // Do not include raw keys in auth records or logs.
    public record IssuedKey(String keyId, String value, Instant expiresAt) {
        @Override
        public String toString() {
            return "IssuedKey(keyId=" + keyId
                    + ", value=[REDACTED], expiresAt=" + expiresAt + ")";
        }
    }

    public record KeyRow(
            String keyId,
            String clientId,
            String tenantId,
            byte[] verifier,
            Set<String> permissions,
            Instant notBefore,
            Instant expiresAt,
            Instant revokedAt) {

        public KeyRow {
            verifier = verifier.clone();
            permissions = Set.copyOf(permissions);
        }

        @Override
        public byte[] verifier() {
            return verifier.clone();
        }
    }

    public static final class InMemoryApiKeyStore {
        private static final Pattern FORMAT = Pattern.compile(
                "^ak1_([A-Za-z0-9_-]{22})\\.[A-Za-z0-9_-]{43}$");

        private static final Set<String> SUPPORTED_PERMISSIONS =
                Set.of("orders:read", "orders:write");

        private final SecureRandom random = new SecureRandom();
        private final ConcurrentMap<String, KeyRow> rows =
                new ConcurrentHashMap<>();
        private final Clock clock;

        public InMemoryApiKeyStore(Clock clock) {
            this.clock = clock;
        }

        // Call only from authenticated + authorized key-issuance workflows.
        // The returned value is displayed exactly once to the recipient.
        public IssuedKey issue(String clientId,
                               String tenantId,
                               Set<String> permissions,
                               Duration ttl) {

            if (clientId == null || clientId.isBlank()
                    || tenantId == null || tenantId.isBlank()
                    || permissions == null || permissions.isEmpty()
                    || !SUPPORTED_PERMISSIONS.containsAll(permissions)
                    || ttl == null || ttl.isNegative() || ttl.isZero()
                    || ttl.compareTo(Duration.ofDays(30)) > 0) {
                throw new IllegalArgumentException("Invalid key policy");
            }

            Instant now = clock.instant();
            Instant expires = now.plus(ttl);

            // putIfAbsent preserves ID uniqueness under concurrent issuance.
            while (true) {
                String id = urlSafeRandom(16);       // 22 chars
                String secret = urlSafeRandom(32);   // 43 chars
                String raw = "ak1_" + id + "." + secret;

                KeyRow row = new KeyRow(
                        id, clientId, tenantId,
                        sha256(raw), permissions, now, expires, null);
                if (rows.putIfAbsent(id, row) == null) {
                    return new IssuedKey(id, raw, expires);
                }
            }
        }

        public Mono<KeyRow> findActive(String raw) {
            return Mono.defer(() -> {
                if (raw == null) {
                    return Mono.empty();
                }

                Matcher matcher = FORMAT.matcher(raw);
                if (!matcher.matches()) {
                    return Mono.empty();
                }

                KeyRow row = rows.get(matcher.group(1));
                if (row == null) {
                    return Mono.empty();
                }

                Instant now = clock.instant();
                boolean active = row.revokedAt() == null
                        && !now.isBefore(row.notBefore())
                        && now.isBefore(row.expiresAt());

                if (!active || !MessageDigest.isEqual(
                        row.verifier(), sha256(raw))) {
                    return Mono.empty();
                }
                return Mono.just(row);
            });
        }

        // Revocation is a one-way transition: there is no "unrevoke".
        public void revoke(String keyId) {
            rows.computeIfPresent(keyId, (ignored, previous) -> {
                if (previous.revokedAt() != null) {
                    return previous;
                }
                return new KeyRow(
                        previous.keyId(),
                        previous.clientId(),
                        previous.tenantId(),
                        previous.verifier(),
                        previous.permissions(),
                        previous.notBefore(),
                        previous.expiresAt(),
                        clock.instant());
            });
        }

        // For test fixtures only; never expose a public endpoint to clear the store.
        public void clearForTest() {
            rows.clear();
        }

        private String urlSafeRandom(int byteCount) {
            byte[] bytes = new byte[byteCount];
            random.nextBytes(bytes);
            return Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(bytes);
        }

        private static byte[] sha256(String raw) {
            try {
                return MessageDigest.getInstance("SHA-256")
                        .digest(raw.getBytes(StandardCharsets.US_ASCII));
            } catch (NoSuchAlgorithmException failure) {
                throw new IllegalStateException(
                        "Java runtime lacks SHA-256", failure);
            }
        }
    }

    @RestController
    public static class OrdersController {

        @GetMapping("/api/orders/{tenantId}")
        public Mono<String> read(@PathVariable String tenantId) {
            return replyForTenant(tenantId, "read");
        }

        @PostMapping("/api/orders/{tenantId}")
        public Mono<String> write(@PathVariable String tenantId) {
            return replyForTenant(tenantId, "write");
        }

        private Mono<String> replyForTenant(
                String requestedTenant, String action) {
            return ReactiveSecurityContextHolder.getContext()
                    .flatMap(context -> {
                        ApiClient actor = (ApiClient) context
                                .getAuthentication().getPrincipal();

                        // Block cross-tenant access even if the key has a valid scope.
                        if (!actor.tenantId().equals(requestedTenant)) {
                            return Mono.error(new ResponseStatusException(
                                    HttpStatus.FORBIDDEN));
                        }

                        return Mono.just(action + ":" + requestedTenant
                                + ":" + actor.clientId());
                    });
        }
    }
}
```

### 4.1. Why This Pattern Fits WebFlux

- `AuthenticationWebFilter` is the standard `WebFilter` in **Spring Security Reactive**. `ServerAuthenticationConverter` extracts the credential from `ServerWebExchange` into an unauthenticated `Authentication`.
- `ReactiveAuthenticationManager` looks up the key record and constructs the 3-argument `UsernamePasswordAuthenticationToken` with principal + authorities **only after the verifier and validity checks pass**.
- `AuthenticationWebFilter` attaches the authenticated result to the Reactor Context for downstream stages; controllers read it via `ReactiveSecurityContextHolder`. There is no `HttpServletRequest`, `OncePerRequestFilter`, or mutable `ThreadLocal`.
- `NoOpServerSecurityContextRepository` ensures authentication is not persisted across requests as a session. Every request sends the key again. This is a trade-off: each request verifies the key, so you need a fast lookup store and a safe caching strategy.
- `@Order(0)` and `securityMatcher("/api/**")` scope the API chain. The `@Order(1)` chain denies remaining paths in the fixture, preventing accidental exposure of new endpoints. In applications with OAuth2/browser UI, replace the fallback chain with one designed for web routes.
- `hasAuthority("KEY_orders:read")` checks the exact authority derived from per-key permissions. `hasRole("read")` is **different** because it looks for a `ROLE_` prefix by default; never mix API key scopes with user roles.
- Missing/invalid/expired/revoked keys return 401 via the entry point/failure handler with the `WWW-Authenticate: ApiKey realm="orders"` challenge, without revealing whether a key exists or why it failed.
- The raw value stays only in `credentials` on the incoming token prior to manager validation. The authenticated `Authentication` has `credentials=null`; the principal holds only ID/tenant/key ID, never the secret.

### 4.2. Intentional Limitations of the Fixture

This example has a complete testable flow yet **is not production-ready as-is**:

1. `InMemoryApiKeyStore` uses single-process RAM, loses data on restart, and does not share state across scaled pods. Production must replace it with a durable Reactive repository as the single source of truth, without wrapping blocking JDBC inside `Mono.fromCallable(...)` directly on the event loop.
2. `issue()` is a Java method used by tests; it **is not an administrative API**. For real-world issuance/revocation, place it behind strong identity (admin/OAuth2/mTLS), caller authentication, scope approval, tenant checks, rate limiting, auditing, and CSRF protection if managed through a browser.
3. The 30-day maximum lifetime and permission set are **illustrative policy values**, not guaranteed defaults of Spring Security. Real lifetimes should reflect risk, deployment cadence, and automated management.
4. The `X-API-Key` header is a convention for this lab; an `Authorization: ApiKey ...` scheme works too. Do not enable both credential extraction paths simultaneously unless policy is consistent and proxies handle both cleanly.
5. The demo disables CSRF **only on the header-only chain** that does not rely on cookies for credentials. If an API accepts cookies/sessions or browser-attached credentials, evaluate CSRF and keep matching protection.
6. If a gateway/ingress logs all request headers, the key still leaks before reaching the application. Configure **redaction at every hop**, TLS, header size limits, and avoid forwarding keys to downstream services unless authorized.

## 5. Gradle Dependencies and Running Application

Add this snippet to `build.gradle` in a Spring Boot 3.x / Java 17+ project using Boot dependency management. This is a **build configuration snippet**, not a standalone Gradle file:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

`ApiKeySecurityConfig` is a Spring `@Configuration` class. When placed in a component-scanned package of a Spring Boot application, the store bean and filter chains are registered. `OrdersController` in the example is a nested `@RestController`: the test fixture below **explicitly imports** it to guarantee endpoint registration. In a real app, you can move the controller to its own file in a scanned package.

To run the application directly, create an entry point in the parent package, for example:

```java
package example.apikey;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Import;

@SpringBootApplication
@Import(ApiKeySecurityConfig.OrdersController.class)
public class ApiKeyApplication {
    public static void main(String[] args) {
        SpringApplication.run(ApiKeyApplication.class, args);
    }
}
```

File `src/main/java/example/apikey/ApiKeyApplication.java` is only for standalone execution. **No valid API key exists automatically after boot**, because the demo intentionally exposes no key-creation endpoint. The JUnit test below issues keys for testing. In production, bootstrap/management workflows issue keys through a secure channel without printing keys to stdout or startup logs.

## 6. Automated WebTestClient Testing: Auth, Permissions, Tenant, Rotation

File `src/test/java/example/apikey/ApiKeySecurityTest.java`:

```java
package example.apikey;

import java.time.Duration;
import java.util.Set;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(
        classes = ApiKeySecurityTest.TestApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@Execution(ExecutionMode.SAME_THREAD)
class ApiKeySecurityTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    ApiKeySecurityConfig.InMemoryApiKeyStore store;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        store.clearForTest();
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void missingMalformedAndDuplicateHeadersAre401() {
        client.get().uri("/api/orders/tenant-a")
                .exchange()
                .expectStatus().isUnauthorized();

        client.get().uri("/api/orders/tenant-a")
                .header("X-API-Key", "guess")
                .exchange()
                .expectStatus().isUnauthorized();

        var issued = store.issue(
                "batch-importer", "tenant-a",
                Set.of("orders:read"), Duration.ofHours(1));

        client.get().uri("/api/orders/tenant-a")
                .header("X-API-Key", issued.value(), issued.value())
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void readOnlyKeyCanReadButCannotWriteOrChangeTenant() {
        var readOnly = store.issue(
                "batch-importer", "tenant-a",
                Set.of("orders:read"), Duration.ofHours(1));

        client.get().uri("/api/orders/tenant-a")
                .header("X-API-Key", readOnly.value())
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("read:tenant-a:batch-importer");

        client.post().uri("/api/orders/tenant-a")
                .header("X-API-Key", readOnly.value())
                .exchange()
                .expectStatus().isForbidden();

        client.get().uri("/api/orders/tenant-b")
                .header("X-API-Key", readOnly.value())
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void writeGrantIsExplicitAndStillTenantBound() {
        var readWrite = store.issue(
                "batch-importer", "tenant-a",
                Set.of("orders:read", "orders:write"),
                Duration.ofHours(1));

        client.post().uri("/api/orders/tenant-a")
                .header("X-API-Key", readWrite.value())
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("write:tenant-a:batch-importer");

        client.post().uri("/api/orders/tenant-b")
                .header("X-API-Key", readWrite.value())
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void rotationAllowsOverlapThenRevokesOnlyOldKey() {
        var oldKey = store.issue(
                "partner-1", "tenant-a",
                Set.of("orders:read"), Duration.ofHours(1));

        var nextKey = store.issue(
                "partner-1", "tenant-a",
                Set.of("orders:read"), Duration.ofHours(1));

        client.get().uri("/api/orders/tenant-a")
                .header("X-API-Key", oldKey.value())
                .exchange()
                .expectStatus().isOk();

        client.get().uri("/api/orders/tenant-a")
                .header("X-API-Key", nextKey.value())
                .exchange()
                .expectStatus().isOk();

        store.revoke(oldKey.keyId());

        client.get().uri("/api/orders/tenant-a")
                .header("X-API-Key", oldKey.value())
                .exchange()
                .expectStatus().isUnauthorized();

        client.get().uri("/api/orders/tenant-a")
                .header("X-API-Key", nextKey.value())
                .exchange()
                .expectStatus().isOk();
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import({
            ApiKeySecurityConfig.class,
            ApiKeySecurityConfig.OrdersController.class
    })
    static class TestApplication {}
}
```

**Expected results:**

| Case | Response |
| --- | --- |
| Missing header, bad format, duplicate headers | `401 Unauthorized` |
| Read-only key GET on matching tenant | `200 OK`, body `read:tenant-a:batch-importer` |
| Read-only key POST | `403 Forbidden` |
| Valid key accessing another tenant | `403 Forbidden` |
| Key with write grant, POST on matching tenant | `200 OK`, body `write:tenant-a:batch-importer` |
| Old + new before revoke | Both `200 OK` |
| Old after revoke, new still active | Old `401`; new `200` |

Tests use credentials generated by `SecureRandom`, never hardcode raw keys, and never print keys. `WebTestClient.bindToApplicationContext(...).apply(springSecurity())` exercises the WebFlux filter chain inside the application context, touching **converter → manager → authorization → controller**. `@Execution(SAME_THREAD)` prevents concurrent test cases from interfering with the shared in-memory store in the same application context.

Run from the Gradle project with wrapper:

```bash
./gradlew test --tests 'example.apikey.ApiKeySecurityTest'
```

On Windows:

```powershell
.\gradlew.bat test --tests "example.apikey.ApiKeySecurityTest"
```

`gradlew test` compiles and runs JUnit on Java 17+. There are no mandatory business stdout lines because the fixture prints neither secrets nor results to the console. When all 4 `@Test` methods pass the listed assertions, Gradle reports the test task successful. This code targets Spring Boot 3.x / Spring Security 6.x on Java 17+ and may need adjustments for other versions/frameworks; never apply Servlet APIs to WebFlux.

### 6.1. Testing Expiration Without Flaky Sleeps

In `InMemoryApiKeyStore`, time is read from `Clock`. When writing store-level tests, use `Clock.fixed(instant, ZoneOffset.UTC)` to test immediately before/after `expiresAt`, or inject a mutable `Clock` in test fixtures. Scenarios must verify:

- `now < notBefore` → 401.
- `notBefore <= now < expiresAt`, valid digest, and not revoked → 200 if scopes suffice.
- `now == expiresAt` or `now > expiresAt` → 401.
- Revocation causes immediate rejection even when `expiresAt` is far in the future.

Prefer a deterministic clock over `Thread.sleep(1000)`. System clocks across replicas must be synchronized; if the backend permits skew, expiration rules must be clearly defined.

## 7. Controlled Key Rotation: Operational Steps

**You cannot rotate keys by mutating the verifier of the same ID** if you want the old and new keys managed independently. Create a **new record**, using `rotation_group` or `replaced_key_id` to track the rotation chain.

Suppose partner `partner-1`, tenant `tenant-a` has key `K1` with `orders:read` only:

```text
T0: K1 active                       -> K1 200; K2 does not exist yet
T1: issue new K2, scope=orders:read -> K1 200; K2 200
T2: deliver K2 via secure channel   -> client deploys K2; K1 still valid briefly
T3: verify K2 on live traffic       -> logs by keyId; confirm K2 receives traffic
T4: revoke K1 (revoked_at=now)      -> K1 401; K2 200
T5: K2 expires or next rotation     -> must issue K3 before K2 expires
```

Workflow:

1. **Request and approval:** verify client/tenant, purpose, endpoint list, scopes, and expiry. The new key retains only required scopes; if the client requests broader permissions, run a separate approval workflow.
2. **Issue new key:** generate an independent ID and secret with RNG, save hash/metadata in a transaction while keeping K1 active, and record who/when/why plus `rotation_group`.
3. **One-time secret delivery:** deliver via secret manager/vault or secure channel to the customer; never send plaintext in email, issue trackers, CI logs, or dashboards that re-display secrets. Configure clients to adopt new keys without full-system restarts whenever possible.
4. **Overlap window:** test one permitted GET/POST with K2 and one scope-denied call; monitor `key_id`, 401/403 rates, and usage. K1 and K2 coexist only for the approved migration window.
5. **Revoke K1:** set `revoked_at` one-way in the primary data store, invalidate caches by key ID, and verify all replicas see the updated state.
6. **Verification:** new requests with K1 must return 401, while K2 continues returning 200 and remains bounded by scope/tenant. Confirm no client still sends K1 and update inventory/audit. Purge the old secret on the client and secret manager once safe.
7. **Emergency response:** if there is evidence K1 was compromised, revoke **immediately**, accepting necessary disruption instead of waiting for overlap. Rotate related downstream credentials and investigate unauthorized usage.

**Consistency window:** revocation takes effect at the time of each request's check. A request that passed authentication just before the revoke commit may still be in flight; for critical irreversible actions, re-check key status at the business commit step or design fencing/transactions accordingly. With TTL caches, revocation may lag by up to the TTL plus invalidation latency. Therefore, document a **revocation SLO** (measurable bound) rather than claiming “instant revocation” while pods hold stale caches.

### 7.1. Distinguishing Rotate, Renew, and Scope Elevation

- **Rotate:** generate a new key ID/secret, keep privileges per policy, and revoke the old key after transition.
- **Renew:** extend expiration/version only if policy allows; for high-risk systems, issuing a new key is safer than extending an old secret indefinitely.
- **Scope elevation:** not a routine rotation; requires an independent authorization decision, tenant/resource review, and auditing.
- **Revoke:** make the current key rejected. Never “unrevoke” to restore a previously leaked key.
- **Expire:** the system rejects keys automatically once `expires_at` is reached, even without a cleanup job deleting rows. Cleanup jobs are solely for housekeeping, not security enforcement.

## 8. Moving from In-Memory to a Durable Store

Example PostgreSQL DDL to illustrate structure (not a universal migration for every database):

```sql
CREATE TABLE api_keys (
    key_id              varchar(22) PRIMARY KEY,
    client_id           text NOT NULL,
    tenant_id           text NOT NULL,
    verifier_sha256     bytea NOT NULL,
    not_before          timestamptz NOT NULL,
    expires_at          timestamptz NOT NULL,
    revoked_at          timestamptz NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    created_by          text NOT NULL,
    rotation_group      text NOT NULL,
    CONSTRAINT verifier_length CHECK (octet_length(verifier_sha256) = 32),
    CONSTRAINT valid_times CHECK (expires_at > not_before)
);

CREATE TABLE api_key_permissions (
    key_id      varchar(22) NOT NULL
                REFERENCES api_keys(key_id) ON DELETE CASCADE,
    permission  text NOT NULL,
    PRIMARY KEY (key_id, permission)
);
```

A child permissions table supports auditing and unique permissions, but issuance must run in a **transaction**: insert parent + permissions in the same commit. Keep constraints preventing rows from expiring before activation. On revocation:

```sql
UPDATE api_keys
SET revoked_at = CURRENT_TIMESTAMP
WHERE key_id = :key_id AND revoked_at IS NULL;
```

This is illustrative **parameterized SQL**; `:key_id` is a DB client bind placeholder—never concatenate HTTP values into SQL strings. To track `last_used_at`, use bounded async events/batches rather than executing a hot row write transaction on every request. Client and tenant identities must come from the DB after authentication, never from client-supplied headers.

A production repository should provide:

- `findByKeyId` returning `Mono<KeyRow>` via R2DBC/a reactive driver, loading permissions cleanly without uncontrolled N+1 queries.
- Issuance/rotation/revocation inside transactions with operator authorization, quotas, unique key IDs, and audit logs.
- A caching strategy: short-TTL metadata cache per key ID or per-request DB lookup, active invalidation on revocation, measured worst-case lag, and failover testing.
- During verifier store outages, fail **closed**: never authenticate unverified keys. Separate **infrastructure errors** from invalid credentials in metrics/logs; do not blindly coerce every infrastructure failure into 401.
- Multi-instance deployments must not rely on process memory; owner and scope data must be consistent. Use UTC timestamps and synchronized clocks.
- Each service should have read-only access to the verifier/metadata it needs for authentication; **create/revoke** privileges belong to a dedicated management service with its own identity and policies.
- Database encryption at rest, backups, RBAC, audit logs, and a secret manager for sensitive components. Digests cannot reconstruct raw keys.

**Never** wrap `Mono.fromCallable(() -> jdbcRepository.findById(...))` directly on the event loop and call it “reactive.” If blocking sources must be integrated, isolate them onto an appropriate scheduler with bounded thread pools, or migrate to truly reactive access.

## 9. Extended Pre-Production Test Matrix

| Scenario | Trigger condition | Expected outcome |
| --- | --- | --- |
| Missing header | Protected GET route | 401 with appropriate challenge |
| Duplicate/malformed header | Two `X-API-Key` headers or regex mismatch | 401 without revealing key ID existence |
| Non-existent ID | Well-formed public ID not in store | 401 without leaking details |
| Wrong secret | Existing ID with 1-byte altered secret | 401 |
| Future `notBefore` | Valid digest not yet active | 401 |
| Expired key | `now >= expiresAt` | 401 |
| Revoked key | `revoked_at != null` | 401 |
| Read key GET matching tenant | Has `orders:read` | 200 with data only for the key's tenant |
| Read key POST | Lacks `orders:write` | 403, no side effect |
| Write key POST matching tenant | Has `orders:write` | 200 when business logic succeeds |
| Read key different tenant | GET tenant B with tenant A's key | 403 or deny per policy, no data leak |
| Route outside allowlist | `PATCH /api/orders/...` | 403/deny per policy |
| K1 and K2 overlap | Both active, same scopes | Both requests succeed |
| K1 after revoke | K1 revoked, K2 active | K1 401, K2 200 |
| Multi-pod | Revoke via pod A, call pod B | Pod B rejects K1 within revocation SLO |
| Unauthorized scope elevation | Issuance requested above operator privileges | 403/deny at management boundary |
| Key header through proxy | TLS termination, ingress/gateway | Key forwarded once and redacted in logs |
| Key leaked in logs | Inspect APM logs, traces, reverse proxy, error bodies | Zero raw keys; only policy-approved key ID audit |
| Verifier store outage | DB unreachable | Never fail open; distinct metrics/alerts |
| Races | Revocation concurrent with multiple requests | In-flight rules, consistency, and revocation lag measured |
| Rate limits | Repeated guessing of key IDs/secrets | Throttled without arbitrarily blocking unrelated tenants |

Not every error must share the exact same HTTP status during infrastructure failures; just ensure **unverified credentials are never accepted**. 401/403 responses may be standardized at the gateway per API contract; all layers must preserve semantics without leaking sensitive causes.

### 9.1. Tenant Authorization Tests Must Use Real Data

The `OrdersController` fixture returns strings to highlight the guard condition. In a real application, use queries with mandatory constraints:

```sql
SELECT id, tenant_id, amount
FROM orders
WHERE id = :order_id AND tenant_id = :authenticated_tenant_id;
```

`authenticated_tenant_id` comes from the verified `ApiClient` in Reactor Context, **never** directly from route parameters or JSON bodies. For UPDATE/DELETE, include the same tenant condition in `WHERE` and verify affected row counts. A key granted `orders:read` must never access another partner's data simply by knowing its ID.

### 9.2. Load, Brute Force, and Latency

Issuing unbounded keys without quotas bloats metadata; brute-forcing public IDs can drive DB queries even though guessing a 256-bit secret is infeasible. Apply controlled rate limiting keyed by **client identity, valid key ID, IP/CIDR, and edge rules**; use backoff/alerts on abnormal 401 spikes without locking out entire tenants merely because an attacker knows a public ID. Caching an authorized result must respect revocation and expiration; never cache `Authentication` globally across requests or let key A receive key B's scopes.

Useful metrics: active keys per client, expiring keys, rotation counts, time from revocation to cluster-wide denial, 401/403 rates per route, verifier lookup latency, and 5xx errors from the key store. Log only filtered `key_id`, client ID, request ID, outcome, and timestamp; if security policy forbids logging raw key IDs directly, log a safe fingerprint or reference ID. Never log raw keys in queries, bodies, headers, or stack traces.

## 10. Common Design Mistakes

### 10.1. Writing a Custom `WebFilter` That Stores the Principal Globally

Wrong: storing `static Authentication currentUser` or a `ThreadLocal` in a filter for controllers to read. Reactor can switch threads or interleave multiple subscriptions; this causes **identity and permission leaks**. Right: `AuthenticationWebFilter` + `ReactiveAuthenticationManager` + subscription-scoped `ReactiveSecurityContextHolder`. Never call `subscribe()` manually inside auth services; return publishers for the framework to subscribe to.

### 10.2. Weak Hashing or Short Secrets

Wrong: user-chosen 8-character keys hashed with `SHA-256` and treated as secure. Fast digests of low-entropy secrets fall quickly to offline brute force after a DB leak. Right: `SecureRandom`-generated keys with ≥256 bits of entropy, strict format checks, stored verifiers, and constant-time digest comparison instead of `String.equals`. Revisit the threat model when stronger DB-breach resistance is required; consider versioned server-side peppers/KMS with separate governance.

### 10.3. Mutating an Existing Key Instead of Issuing a New One

Wrong: updating `verifier_sha256` on row K1 and immediately demanding clients swap secrets, causing 401s on K1 before clients roll out. Right: create K2, maintain a controlled overlap, confirm K2, then revoke K1. For compromised keys, prioritize emergency revocation over rollout convenience.

### 10.4. Granting Permissions at the Client Level Rather Than Per Key

Wrong: every key belonging to a client inherits all client permissions, so a read-only reporting key also gains write/delete access. Right: derive authorities directly from the **calling key's** verified record, checking method/path + tenant/resource. Issuing a new key must never exceed approved permissions.

### 10.5. Confusing “Stateless” with Having No State Store

API key validation typically requires metadata lookups to verify expiry, scopes, and revocation. An API that is stateless at the **HTTP session** layer still maintains credential lifecycle state in a data store. Hashing raw keys without tracking revocation state prevents revoking keys flexibly prior to expiration.

### 10.6. Sharing One Filter Chain for Browser Login and API Keys

If a custom API key filter matches every request, it can break OAuth2 login, CORS preflight, health endpoints, or session authentication. Right: configure `securityMatcher` and `@Order`, using a dedicated chain for machine-to-machine APIs; consider handling CORS preflight before auth when official browser clients exist. For session-based browsers, never disable CSRF just to “avoid 403.”

### 10.7. Revoking in One Instance While Caches and Other Pods Still Accept the Key

Wrong: deleting a key from RAM on one instance and declaring it revoked. Right: central store + transactions + invalidation + multi-pod verification; measure actual revocation lag. For irreversible high-value actions, re-verify key version/revocation inside the critical business step.

### 10.8. Exposing Raw Keys Through Provisioning and Observability

Wrong: admin APIs returning raw keys multiple times, default record `toString()` printing secrets, exceptions printing `X-API-Key`, reverse proxies dumping all headers, or backups holding plaintext. Right: show once, return `Cache-Control: no-store` on issuance responses, enforce TLS, use a secret manager, redact logs, store only digests, and audit the lifecycle.

## 11. Troubleshooting 401/403 Errors

```text
Client sends X-API-Key and receives an error
 |
 +-- Does the request reach the app through proxy/ingress?
 |     +-- No: check HTTPS, proxy auth, header forwarding, routing
 |     +-- Yes:
 |         |
 |         +-- Is the /api/** chain selected? Does converter read 1 header?
 |         |      +-- No: check securityMatcher, @Order, route/prefix
 |         |      +-- Yes:
 |         |          |
 |         |          +-- Are format and key ID lookup valid?
 |         |          |      +-- No: 401
 |         |          |      +-- Yes:
 |         |          |          |
 |         |          |          +-- Digest, notBefore, expiresAt, revokedAt?
 |         |          |          |      +-- Fail: 401
 |         |          |          |      +-- Pass:
 |         |          |          |          |
 |         |          |          |          +-- Per-key authority matches?
 |         |          |          |          |      +-- No: 403
 |         |          |          |          |      +-- Yes: check tenant/owner in business logic
 |
 +-- Fails only on other pods: check shared store/cache/clocks
 +-- Fails during rotation: check K2 rollout, K1 revoked_at, TTL, invalidation
 +-- Key accepted yet another tenant's data leaks: inspect DB predicates immediately
```

Prefer tracking **authentication and authorization status** per request via request ID without printing raw secrets. Distinguish missing/invalid credentials (401), valid key lacking permission (403), dependency failures like DB timeouts (5xx or policy-defined status), and unmatched routes (404). When investigating “revocation did not work,” test the same key against every replica right after the revoke commit, measure cache invalidation, and verify no other system is authenticating keys outside the managed store.

## 12. Acceptance Checklist

- [ ] Uses a versioned format `ak1_<id>.<secret>`, random public ID, and 256-bit secret from a CSPRNG.
- [ ] Displays keys only upon issuance; stores only digest/verifier, metadata, and per-key scopes; raw keys never appear in logs/URLs.
- [ ] `AuthenticationWebFilter` runs on the right WebFlux chain/routes; converter handles missing/duplicate/malformed headers.
- [ ] `ReactiveAuthenticationManager` verifies digest securely, `notBefore`, expiry, and revoked state before building `Authentication`.
- [ ] Stateless API chain does not save auth into `WebSession`; controllers receive the principal via Reactor Context.
- [ ] GET/POST enforce distinct authorities; deny by default; tenant/object-level checks are enforced in real data queries.
- [ ] Read-only keys cannot write, and tenant A keys cannot read/write tenant B.
- [ ] Rotation creates K2, verifies overlap, revokes K1, tests K1 → 401 and K2 → 200; emergency revocation has a dedicated path.
- [ ] Production store uses a durable Reactive repository, transactions, isolated issuance/revocation permissions, and shared state across replicas.
- [ ] Expiry/revocation are verified deterministically, with a revocation SLO and cache/replica testing.
- [ ] TLS, gateway/ingress, rate limiting, auditing, and log redaction are configured; keys are never shipped to browsers.
- [ ] Unit/integration `WebTestClient` tests cover missing/malformed/wrong/valid/insufficient-permission/tenant/rotation cases and verify system errors fail closed.

## References

- [Spring Security — AuthenticationWebFilter Javadoc (Reactive)](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html).
- [Spring Security — WebFlux Security Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html).
- [Spring Security — Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html).
- [Spring Security — SecurityWebFiltersOrder and ServerHttpSecurity](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/config/web/server/ServerHttpSecurity.html).
- [Spring Security — NoOpServerSecurityContextRepository](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/context/NoOpServerSecurityContextRepository.html).
- [Spring Security — Testing WebFlux Security with WebTestClient](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html).
- [Oracle Java — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html) and [MessageDigest.isEqual](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html).
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet).
- [OWASP — REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet).
