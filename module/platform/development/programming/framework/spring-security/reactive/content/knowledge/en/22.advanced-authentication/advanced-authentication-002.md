# Creating a Specialized Authentication Token and ServerAuthenticationConverter

## Learning Objectives

This lesson is part of **Advanced Authentication** in **Spring Security reactive (Spring WebFlux)**. After this lesson, you will be able to:

- Distinguish between `Authentication`, `AbstractAuthenticationToken`, `ServerAuthenticationConverter`, `ReactiveAuthenticationManager`, and `AuthenticationWebFilter`.
- Create a **custom Authentication token** with two clear states: an *unauthenticated* request (credential candidate, no authorities) and an *authenticated* result (server-assigned principal + authorities, carrying no raw secret).
- Write a converter returning `Mono<Authentication>` from `ServerWebExchange`; distinguish **missing credential** → `Mono.empty()`, **credential present** → unauthenticated token, **malformed header** → `Mono.error(AuthenticationException)`.
- Attach the converter and manager to `AuthenticationWebFilter`, scope it with `setRequiresAuthenticationMatcher(...)`, and register it via `ServerHttpSecurity.addFilterAt(..., SecurityWebFiltersOrder.AUTHENTICATION)`.
- Understand success/failure handlers, `NoOpServerSecurityContextRepository`, Reactor Context, 401 vs 403, and authority-based authorization.
- Run a **Java 17, Spring Boot WebFlux** demo with a test API key header, then test the converter/manager/filter chain using `StepVerifier` and `WebTestClient`.
- Avoid pitfalls such as calling `setAuthenticated(true)` before verification, logging credentials, handling duplicate HTTP headers ambiguously, calling `block()/subscribe()` in reactive security, double-registering filters, or disabling security across all routes.

> The example uses an **internal API key header** solely to teach how to extend authentication. Static keys have replay/rotation limitations; production systems should consider OAuth2 Resource Server, mTLS, or signed requests depending on the threat model. Do not use this example to embed a credential in an SPA/browser. The classes in this lesson belong to the **reactive stack**, not Servlet's `HttpSecurity` or `OncePerRequestFilter`.

## 1. Processing Model for a Custom Authentication Method

Suppose a service should only allow calls from an internal batch worker:

~~~http
GET /internal/report HTTP/1.1
Host: service.example.test
X-Internal-Key: <high-entropy-secret>
~~~

Proposed flow:

~~~text
HTTP /internal/report
        |
        v
SecurityWebFilterChain
        |
        v
AuthenticationWebFilter
        |
        +-- setRequiresAuthenticationMatcher("/internal/**")
        |       other request paths -> continue, do not parse key
        |
        v
ServerAuthenticationConverter
        |
        +-- missing X-Internal-Key -> Mono.empty()
        +-- malformed/multiple headers -> Mono.error(BadCredentialsException)
        +-- valid format -> unauthenticated InternalKeyAuthenticationToken
        |
        v
ReactiveAuthenticationManager
        |
        +-- verify credential against trusted server-side source
        +-- invalid -> Mono.error(BadCredentialsException)
        +-- valid -> authenticated Authentication:
        |           principal="batch-reader"
        |           authorities=[SCOPE_internal.read]
        |           credentials=null
        |
        v
ReactiveSecurityContextHolder (within subscription)
        |
        v
authorizeExchange: hasAuthority("SCOPE_internal.read")
        |
        +-- insufficient authority -> 403
        +-- sufficient authority -> Controller returns JSON
~~~

Each component has a distinct responsibility:

| Component | Input | Output | Must Not Do |
|---|---|---|---|
| `ServerAuthenticationConverter` | HTTP request/`ServerWebExchange` | An **unauthenticated** Authentication, or empty/error | Assume the key is valid; self-grant admin role |
| `ReactiveAuthenticationManager` | Authentication candidate | Verified Authentication or error | Trust caller-sent `X-Role`/`X-User` |
| `AuthenticationWebFilter` | Request + converter + manager | SecurityContext for downstream, success/failure | Write blocking HTTP bodies manually or register twice |
| `SecurityWebFilterChain` | HTTP request + Authentication | Endpoint access decision | `permitAll` on internal endpoints |
| Business/service authorization | Principal + policy + resource data | Permit the actual operation | Skip tenant/owner/ACL checks |

**Authentication ≠ Authorization:** A valid key proves who is calling; that key may **not** hold admin privileges. An admin route must still return 403 even when Authentication succeeds.

## 2. Designing a Two-State Authentication Token

The `Authentication` interface in Spring Security represents both an authentication request and an authentication result. Its methods:

| Method | Purpose |
|---|---|
| `getPrincipal()` | Caller identity; trustworthy only after validation |
| `getCredentials()` | Proof passed into the manager |
| `getAuthorities()` | Permissions granted by authentication/authorization policy |
| `isAuthenticated()` | Authentication state recognized by Spring Security |
| `setAuthenticated(boolean)` | State mutation; callers must be blocked from flipping it to true |
| `eraseCredentials()` | Clears sensitive credentials on the object after use |
| `getDetails()` | Additional context, not trusted by itself to grant permissions |
| `getName()` | Principal name for logging and auditing |

`AbstractAuthenticationToken` implements authorities, the authenticated flag, and credential erasure for us, so we extend it rather than implementing the entire interface from scratch.

### 2.1. Before Authentication

~~~text
InternalKeyAuthenticationToken.unauthenticated(rawKey)

isAuthenticated = false
principal       = null
credentials     = rawKey
authorities     = []
~~~

This only proves **the client sent a credential candidate**, not that the key is valid.

### 2.2. After Successful Manager Verification

~~~text
InternalKeyAuthenticationToken.authenticated(
    "batch-reader", [SCOPE_internal.read])

isAuthenticated = true
principal       = "batch-reader" (server-assigned)
credentials     = null
authorities     = [SCOPE_internal.read]
~~~

Principal and authorities are **never taken from caller-supplied HTTP headers**. If the system uses multiple keys, the manager must look up the `keyId` in a trusted store and load the corresponding service identity, tenant, and permissions.

### 2.3. Blocking Self-Elevation

Wrong:

~~~java
// ANTI-PATTERN - caller could be falsely trusted before verification:
InternalKeyAuthenticationToken token = ...;
token.setAuthenticated(true);
return Mono.just(token);
~~~

A safe implementation should:

1. Provide an `unauthenticated(rawKey)` factory with state false and no authorities.
2. Provide a factory creating an authenticated token called only by the **trusted manager** after verification. In multi-module production code, consider restricting factory visibility/package access.
3. Override `setAuthenticated(true)` to throw `IllegalArgumentException`, allowing only a trusted private constructor to call `super.setAuthenticated(true)` when creating a **new object**.
4. After the attempt, clear the raw credential on the request token with `eraseCredentials()`. The authenticated object **must not retain** the raw credential.
5. Never override `toString()` to print the key, or copy the key into `getDetails()` just for "debugging".

Not every protocol needs a custom class. Spring already provides `UsernamePasswordAuthenticationToken`, `JwtAuthenticationToken`, and `BearerTokenAuthenticationToken`; use built-in types when they match the protocol to inherit their validator and exception semantics.

## 3. ServerAuthenticationConverter: empty / just / error Results

Spring Security reactive interface:

~~~java
@FunctionalInterface
public interface ServerAuthenticationConverter {
    Mono<Authentication> convert(ServerWebExchange exchange);
}
~~~

This is a **condensed signature**, not an interface you redeclare yourself. The converter reads parts of `ServerWebExchange` (HTTP headers, parameters, path, or body depending on the protocol) and represents the credential as an Authentication candidate.

| Return | Meaning | Example |
|---|---|---|
| `Mono.empty()` | **No authentication attempt** for the filter to process. | Missing `X-Internal-Key` |
| `Mono.just(unauthenticatedToken)` | Syntactically valid credential; manager must verify. | Single key with valid characters |
| `Mono.error(BadCredentialsException)` | Malformed or duplicate credential/request. | Two `X-Internal-Key` headers, value fails pattern |
| `Mono.error(AuthenticationServiceException)` | Real authentication infrastructure failure (per policy). | Secret database unavailable |
| `Mono.just(authenticatedToken)` | **Inappropriate inside this converter.** | Granting privileges without verification |

### 3.1. A Missing Header Is Not a Malformed Header

Request without a key:

~~~http
GET /internal/report HTTP/1.1
Host: localhost:8080
~~~

The converter returns `Mono.empty()`; `AuthenticationWebFilter` continues the chain. The authorization rule for `/internal/report` still requires an authority, so an anonymous caller receives **401** from the entry point.

If the request has:

~~~http
X-Internal-Key: wrong
~~~

The converter detects an authentication attempt whose format is rejected → `Mono.error(BadCredentialsException)` → the failure handler returns 401. If the format is valid but the secret is wrong, the manager likewise emits `BadCredentialsException`.

Do not return empty for an invalid key, as other filters might treat the request as "no authentication attempted" and fall back to a weaker mechanism when policy forbids it.

### 3.2. Duplicate or Proxy-Concatenated Headers

Variants:

~~~http
X-Internal-Key: first-key-value
X-Internal-Key: second-key-value
~~~

~~~http
X-Internal-Key: first-key-value,second-key-value
~~~

If the protocol allows only **one** key, do not call `getFirst()` and ignore the rest; a proxy or ingress might prioritize a different value, causing header parsing ambiguity. The demo rejects whenever size is not 1 or the value fails the base64url-like regex `[A-Za-z0-9_-]{16,128}`.

This regex and length are **demo formatting only**, not a universal standard. In production, generate keys with a CSPRNG—such as **32 random bytes** unpadded base64url-encoded to 43 characters—with explicit key IDs, rotation, and expiry.

### 3.3. Never Put the Key in the URL or Response

Wrong:

~~~http
GET /internal/report?api_key=top-secret
~~~

URLs commonly end up in browser history, proxy logs, analytics, and traces. A header over TLS is preferable, yet **headers must also be scrubbed** from monitoring and logging. Never include the key value in `BadCredentialsException("Bad key: " + raw)` or error JSON.

## 4. Only ReactiveAuthenticationManager May Verify the Key

Interface:

~~~java
public interface ReactiveAuthenticationManager {
    Mono<Authentication> authenticate(Authentication authentication);
}
~~~

This is an abbreviated signature for explanation. The manager **receives an unauthenticated token** and returns either a verified Authentication or an error.

Demo rules:

- Accept only unauthenticated `InternalKeyAuthenticationToken`; for any other token type, return `Mono.empty()` so manager composition can decide.
- Never trust caller-sent role/tenant data.
- Verify the raw credential against a digest computed from the trusted configured key.
- On mismatch, return `Mono.error(BadCredentialsException)` and never construct an authenticated Authentication.
- On match, construct a **new object** with service principal `batch-reader` and a single authority `SCOPE_internal.read`.
- Erase the raw credential from the request token immediately after reading the value for verification.

### 4.1. Constant-Time Comparison Is Not the Whole Security Model

The demo uses:

~~~java
byte[] expected = sha256(secretFromTrustedConfig);
byte[] presented = sha256(secretFromHeader);

boolean valid = MessageDigest.isEqual(expected, presented);
~~~

This is an **illustrative snippet** (a complete app needs the `sha256` helper). Comparing two fixed-length digests mitigates early-exit character timing issues in `String.equals`. However, it **does not replace**:

- High-entropy keys, rotation/revocation, TTL, and request quotas.
- Secret storage (KMS/secret manager, hashed key database, or HMAC lookup).
- TLS/mTLS, network ACLs, and anti-replay defenses per threat model.
- Input size limits, rate limiting, and attempt monitoring.
- Assigning principal/authorities by `keyId`/tenant from a trusted database.
- Fail-closed behavior on store errors; never treat an exception as a valid credential.

If the secret is short or predictable, comparing SHA-256 digests still does not prevent brute-force guessing. A static key lacks proof-of-possession, so anyone holding the key can replay it until revoked.

### 4.2. Mono.error vs Mono.empty in the Manager

For a manager handling multiple credential types:

~~~java
if (!(authentication instanceof InternalKeyAuthenticationToken)) {
    return Mono.empty(); // does not handle this type
}
~~~

However, when the token **matches the type and the key is wrong**, it must return:

~~~java
return Mono.error(
    new BadCredentialsException("Invalid credential"));
~~~

Do not return empty for an invalid key when policy requires fail-closed behavior. On downstream 500/timeouts from a secret store, map to an appropriate service-authentication failure; never mark authenticated or fall back to a default key.

## 5. AuthenticationWebFilter and SecurityWebFilterChain

The `AuthenticationWebFilter` Javadoc describes the order:

1. Check whether the request matches `setRequiresAuthenticationMatcher(...)`.
2. Run `ServerAuthenticationConverter.convert(exchange)`.
3. If the converter is empty, skip authentication and continue the filter chain.
4. If a candidate is emitted, invoke `ReactiveAuthenticationManager`.
5. On success, the success handler continues the chain with the SecurityContext in the **Reactor Context**; on failure, the failure handler runs.
6. The authorization filter then checks authorities and endpoint access.

Configuration:

~~~java
AuthenticationWebFilter filter =
    new AuthenticationWebFilter(manager);

filter.setServerAuthenticationConverter(
    new InternalKeyAuthenticationConverter());

filter.setRequiresAuthenticationMatcher(
    new PathPatternParserServerWebExchangeMatcher(
        "/internal/**"));

filter.setSecurityContextRepository(
    NoOpServerSecurityContextRepository.getInstance());

HttpStatusServerEntryPoint unauthorized =
    new HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED);

filter.setAuthenticationFailureHandler(
    new ServerAuthenticationEntryPointFailureHandler(
        unauthorized));

http.addFilterAt(
    filter, SecurityWebFiltersOrder.AUTHENTICATION);
~~~

This is a configuration snippet to place inside `@Bean SecurityWebFilterChain`. **Do not** register the filter both as a global `@Bean WebFilter` and via `addFilterAt`: it may execute twice.

### 5.1. A Matcher Is Not an Authorization Rule

- `setRequiresAuthenticationMatcher("/internal/**")` only controls **where authentication is attempted**.
- `authorizeExchange(...hasAuthority(...))` controls **endpoint access**.
- If you leave `anyExchange().permitAll()` on a private endpoint, a custom filter alone does not enforce access control.
- If a request lacks a key, the filter yields empty, yet private authorization still blocks it.
- If a public route lies outside the matcher, the filter ignores the key even if a malformed header is sent; this is intentional behavior that should be tested.

### 5.2. NoOp Security Context Means Stateless, Not "No Principal"

`NoOpServerSecurityContextRepository.getInstance()` does not save Authentication to a session for future requests. Yet the current request still has an authenticated principal in its Reactor Context. Thus:

~~~text
GET /internal/report + valid key
    → manager verifies
    → current request is authenticated
    → controller receives principal
    → next request without key still gets 401
~~~

For form login/session cookies, `NoOp` is normally **inappropriate** because login sessions require persistence. This demo applies only to header-only service authentication.

### 5.3. Why Configure a Custom Failure Handler and Authentication Entry Point

`AuthenticationWebFilter` defaults to failure behavior suited for HTTP Basic. For header-only API keys, you usually want to return **401** without a Basic challenge or form redirect.

- Header present but invalid → the filter's `ServerAuthenticationFailureHandler`.
- No header → converter returns empty; authorization requires auth → `ServerHttpSecurity.exceptionHandling(...authenticationEntryPoint(...))`.
- Valid key but missing role on `/internal/admin` → authorization denied (403), not a credential error.

In the demo, both authentication failure paths use `HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED)`. If returning a custom JSON error body, never echo keys, hashes, or stack traces.

### 5.4. Never Block on the Reactor Netty Event Loop

Do not do this:

~~~java
// ANTI-PATTERN:
public Mono<Authentication> authenticate(Authentication candidate) {
    boolean valid = blockingDatabase.check(candidate).block();
    return Mono.just(...);
}
~~~

The manager should return a reactive pipeline from R2DBC/WebClient/secret store APIs. When a legacy blocking client is unavoidable, use an appropriate scheduler with backpressure and rate limits; never use detached `subscribe()`, which lets the filter proceed before verification finishes.

## 6. Complete Java 17 Example: Header-Only Internal Authentication

**Lab task:** `GET /internal/report` accepts only one valid key; `GET /internal/admin` requires a non-granted authority; `GET /public/ping` is public. The example uses **Spring Boot 3.5.16** (Spring Security reactive 6.5.x via BOM) and Java 17.

### 6.1. Structure

~~~text
reactive-custom-auth/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/CustomAuthApplication.java
    │   └── resources/application.yml
    └── test/
        └── java/example/CustomAuthTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'reactive-custom-auth'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
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
~~~

Requires JDK 17+ and a compatible Gradle or Gradle Wrapper. The demo does **not** include Servlet `spring-boot-starter-web`, so there is no blocking web server.

`src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

app:
  security:
    internal-api-key: ${INTERNAL_API_KEY}
~~~

The placeholder syntax in the actual YAML file is `${INTERNAL_API_KEY}`, **without** a backslash before the dollar sign; the Markdown preserves the authoring presentation. If the env variable is missing, the app must fail on startup instead of falling back to an empty key.

For the local demo, use a **public test key published in this lesson**, never on a real system:

~~~bash
# Linux/macOS:
export INTERNAL_API_KEY='local-demo-key-only-never-use-in-prod-001'
gradle bootRun
~~~

PowerShell:

~~~powershell
$env:INTERNAL_API_KEY = 'local-demo-key-only-never-use-in-prod-001'
gradle bootRun
~~~

Production systems use strong CSPRNG-generated keys managed by a secret manager, never committed to source or shared in terminal history.

### 6.2. Complete Application

File `src/main/java/example/CustomAuthApplication.java`:

~~~java
package example;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.Principal;
import java.util.Collection;
import java.util.List;
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
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
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class CustomAuthApplication {

    public static void main(String[] args) {
        SpringApplication.run(CustomAuthApplication.class, args);
    }

    public static final class InternalKeyAuthenticationToken
        extends AbstractAuthenticationToken {

        private final String principal;
        private String credentials;

        private InternalKeyAuthenticationToken(
            String principal,
            String credentials,
            Collection<? extends GrantedAuthority> authorities,
            boolean trusted) {

            super(authorities);
            this.principal = principal;
            this.credentials = credentials;
            super.setAuthenticated(trusted);
        }

        public static InternalKeyAuthenticationToken unauthenticated(
            String rawKey) {

            return new InternalKeyAuthenticationToken(
                null, rawKey, List.of(), false);
        }

        public static InternalKeyAuthenticationToken authenticated(
            String serviceId,
            Collection<? extends GrantedAuthority> authorities) {

            return new InternalKeyAuthenticationToken(
                serviceId, null, authorities, true);
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
        public void eraseCredentials() {
            super.eraseCredentials();
            credentials = null;
        }

        @Override
        public void setAuthenticated(boolean trusted) {
            if (trusted) {
                throw new IllegalArgumentException(
                    "Use the trusted authenticated factory");
            }
            super.setAuthenticated(false);
        }
    }

    public static final class InternalKeyAuthenticationConverter
        implements ServerAuthenticationConverter {

        @Override
        public Mono<Authentication> convert(
            ServerWebExchange exchange) {

            List<String> headers = exchange.getRequest()
                .getHeaders().getOrEmpty("X-Internal-Key");

            if (headers.isEmpty()) {
                return Mono.empty();
            }

            if (headers.size() != 1) {
                return Mono.error(new BadCredentialsException(
                    "Invalid credential"));
            }

            String raw = headers.get(0);
            if (raw == null
                || !raw.matches("[A-Za-z0-9_-]{16,128}")) {
                return Mono.error(new BadCredentialsException(
                    "Invalid credential"));
            }

            return Mono.just(
                InternalKeyAuthenticationToken.unauthenticated(raw));
        }
    }

    public static final class InternalKeyAuthenticationManager
        implements ReactiveAuthenticationManager {

        private final byte[] expectedDigest;

        public InternalKeyAuthenticationManager(String expectedKey) {
            if (expectedKey == null
                || !expectedKey.matches("[A-Za-z0-9_-]{16,128}")) {
                throw new IllegalArgumentException(
                    "Missing or malformed server secret");
            }
            this.expectedDigest = sha256(expectedKey);
        }

        private static byte[] sha256(String value) {
            try {
                return MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
            } catch (NoSuchAlgorithmException error) {
                throw new IllegalStateException(
                    "SHA-256 is unavailable", error);
            }
        }

        @Override
        public Mono<Authentication> authenticate(
            Authentication authentication) {

            if (!(authentication instanceof
                    InternalKeyAuthenticationToken request)
                || request.isAuthenticated()) {
                return Mono.empty();
            }

            String raw = (String) request.getCredentials();
            request.eraseCredentials();

            boolean valid = raw != null
                && MessageDigest.isEqual(
                    expectedDigest, sha256(raw));

            if (!valid) {
                return Mono.error(new BadCredentialsException(
                    "Invalid credential"));
            }

            return Mono.just(
                InternalKeyAuthenticationToken.authenticated(
                    "batch-reader",
                    List.of(new SimpleGrantedAuthority(
                        "SCOPE_internal.read"))));
        }
    }

    @Bean
    SecurityWebFilterChain security(
        ServerHttpSecurity http,
        @Value("${app.security.internal-api-key}")
        String key) {

        var manager =
            new InternalKeyAuthenticationManager(key);

        var filter = new AuthenticationWebFilter(manager);
        filter.setServerAuthenticationConverter(
            new InternalKeyAuthenticationConverter());

        filter.setRequiresAuthenticationMatcher(
            new PathPatternParserServerWebExchangeMatcher(
                "/internal/**"));

        filter.setSecurityContextRepository(
            NoOpServerSecurityContextRepository.getInstance());

        var unauthorized =
            new HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED);

        filter.setAuthenticationFailureHandler(
            new ServerAuthenticationEntryPointFailureHandler(
                unauthorized));

        return http
            // Only correct for this header-only, cookie-free API.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(unauthorized))
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public/ping")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/internal/report")
                    .hasAuthority("SCOPE_internal.read")
                .pathMatchers(HttpMethod.GET, "/internal/admin")
                    .hasAuthority("ROLE_INTERNAL_ADMIN")
                .anyExchange().denyAll())
            .addFilterAt(
                filter, SecurityWebFiltersOrder.AUTHENTICATION)
            .build();
    }

    @RestController
    static class Endpoints {

        @GetMapping("/public/ping")
        Mono<Map<String, String>> ping() {
            return Mono.just(Map.of("status", "ok"));
        }

        @GetMapping("/internal/report")
        Mono<Map<String, String>> report(
            Mono<Principal> principal) {

            return principal.map(p -> Map.of(
                "service", p.getName(),
                "result", "report-ready"));
        }

        @GetMapping("/internal/admin")
        Mono<Map<String, String>> admin() {
            return Mono.just(Map.of("result", "admin-only"));
        }
    }
}
~~~

### 6.3. Layer-by-Layer Code Analysis

**Token** — `InternalKeyAuthenticationToken.unauthenticated(raw)` holds the raw key, null principal, false state, and empty authorities. Once the manager finishes verifying, the authenticated factory creates a **new** object with server principal `batch-reader` and only the read authority. `setAuthenticated(true)` from callers is blocked; `eraseCredentials()` clears the key.

**Converter** — reads the header once; missing header → empty; duplicate or invalid format → error; valid format → false token **without granting privileges**. The regex `[A-Za-z0-9_-]{16,128}` is only for the lab and does not prove sufficient key entropy.

**Manager** — pre-hashes the trusted key in the constructor; given a candidate, erases the raw credential after taking a local copy, compares fixed-length digests; invalid → `BadCredentialsException`; valid → authenticated token with `SCOPE_internal.read`. In production with multiple keys, look up `keyId` in a trusted store and grant authorities from real metadata.

**Filter** — matcher scopes only to `/internal/**`; failure handler sends 401 rather than a Basic form challenge. `NoOpServerSecurityContextRepository` keeps requests stateless; within a single request, the principal still reaches the controller via Reactor Context.

**Chain** — public `/public/ping`, private `/internal/report` with read scope, `/internal/admin` requiring a role not granted by the demo key, and everything else denied. `SecurityWebFiltersOrder.AUTHENTICATION` ensures the filter runs before authorization. Disabling CSRF is valid only because the demo does **not** use browser session cookies; apps with cookie auth must re-evaluate CSRF.

**Controller** — uses reactive `Mono<Principal>`, never reading the key itself. The response contains only the service name and a report placeholder; no credential is echoed.

### 6.4. Testing Branches with curl

While the backend is running:

~~~bash
# Public:
curl -i http://localhost:8080/public/ping

# Missing credential:
curl -i http://localhost:8080/internal/report

# Wrong key:
curl -i \
  -H 'X-Internal-Key: wrong-local-demo-key-123456789' \
  http://localhost:8080/internal/report

# Correct local-demo credential:
curl -i \
  -H 'X-Internal-Key: local-demo-key-only-never-use-in-prod-001' \
  http://localhost:8080/internal/report

# Correct key, insufficient admin authority:
curl -i \
  -H 'X-Internal-Key: local-demo-key-only-never-use-in-prod-001' \
  http://localhost:8080/internal/admin
~~~

**Expected HTTP results** (field order/headers/status line depend on runtime):

~~~text
GET /public/ping             -> 200 {"status":"ok"}
GET /internal/report no key  -> 401
GET /internal/report bad key -> 401
GET /internal/report good    -> 200 {"service":"batch-reader","result":"report-ready"}
GET /internal/admin good     -> 403
~~~

On PowerShell, you can use `curl.exe`. **Never** pass production keys on the command line/shell history or in logs. The secret strings here are strictly public demo values. The Java code has been structurally reviewed but **not compiled/executed during authoring**, so run it on a compatible JDK/Gradle setup to confirm.

## 7. Testing: Real HTTP Filter Chain and Unit Tests

Use two test layers:

1. `WebTestClient` sends real HTTP headers → flows through converter, manager, filter, and authorization in Spring WebFlux.
2. `StepVerifier` directly verifies token state, converter empty/just/error outputs, manager success/failure, and credential erasure.

**Do not rely solely on `mockAuthentication()`** to claim your converter works: a test mutator that pre-populates Authentication in SecurityContext can **bypass** the custom authentication filter. The HTTP tests here do not mock Authentication.

File `src/test/java/example/CustomAuthTest.java`:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "app.security.internal-api-key=local-demo-key-only-never-use-in-prod-001")
@AutoConfigureWebTestClient
class CustomAuthTest {

    private static final String KEY =
        "local-demo-key-only-never-use-in-prod-001";

    @Autowired
    WebTestClient client;

    private CustomAuthApplication.InternalKeyAuthenticationConverter
        converter() {
        return new CustomAuthApplication
            .InternalKeyAuthenticationConverter();
    }

    @Test
    void publicRouteNeedsNoKey() {
        client.get().uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void missingKeyReturns401() {
        client.get().uri("/internal/report")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void wrongKeyReturns401() {
        client.get().uri("/internal/report")
            .header("X-Internal-Key", "wrong-key-for-this-demo-12345")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void malformedHeaderReturns401() {
        client.get().uri("/internal/report")
            .header("X-Internal-Key", "short")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void duplicateHeadersReturn401() {
        client.get().uri("/internal/report")
            .header("X-Internal-Key", KEY, "second-key-value")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void commaJoinedHeadersReturn401() {
        client.get().uri("/internal/report")
            .header("X-Internal-Key", KEY + ",second-key-value")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void correctKeyCreatesTrustedIdentity() {
        client.get().uri("/internal/report")
            .header("X-Internal-Key", KEY)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.service").isEqualTo("batch-reader")
            .jsonPath("$.result").isEqualTo("report-ready");
    }

    @Test
    void correctKeyDoesNotCreateAdminAuthority() {
        client.get().uri("/internal/admin")
            .header("X-Internal-Key", KEY)
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void publicMatcherDoesNotValidateKey() {
        client.get().uri("/public/ping")
            .header("X-Internal-Key", "not-a-valid-value")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void converterReturnsEmptyWhenNoHeader() {
        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/internal/report").build());

        StepVerifier.create(converter().convert(exchange))
            .verifyComplete();
    }

    @Test
    void converterCreatesOnlyUnauthenticatedRequestToken() {
        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/internal/report")
                .header("X-Internal-Key", KEY).build());

        StepVerifier.create(converter().convert(exchange))
            .assertNext(authentication -> {
                assertInstanceOf(
                    CustomAuthApplication
                        .InternalKeyAuthenticationToken.class,
                    authentication);
                assertFalse(authentication.isAuthenticated());
                assertTrue(authentication.getAuthorities().isEmpty());
                assertEquals(KEY, authentication.getCredentials());
                assertNull(authentication.getPrincipal());
            })
            .verifyComplete();
    }

    @Test
    void converterRejectsDuplicateHeaderDirectly() {
        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/internal/report")
                .header("X-Internal-Key", KEY, "second-key-value")
                .build());

        StepVerifier.create(converter().convert(exchange))
            .expectError(BadCredentialsException.class)
            .verify();
    }

    @Test
    void unauthenticatedTokenCannotBeUpgradedBySetter() {
        var token = CustomAuthApplication
            .InternalKeyAuthenticationToken.unauthenticated(KEY);

        assertFalse(token.isAuthenticated());

        assertThrows(IllegalArgumentException.class,
            () -> token.setAuthenticated(true));

        assertFalse(token.isAuthenticated());
    }

    @Test
    void managerGrantsReadAuthorityAndErasesRawKey() {
        var request = CustomAuthApplication
            .InternalKeyAuthenticationToken.unauthenticated(KEY);

        var manager = new CustomAuthApplication
            .InternalKeyAuthenticationManager(KEY);

        StepVerifier.create(manager.authenticate(request))
            .assertNext(auth -> {
                assertTrue(auth.isAuthenticated());
                assertEquals("batch-reader", auth.getName());
                assertNull(auth.getCredentials());
                assertNull(request.getCredentials());
                assertTrue(auth.getAuthorities().contains(
                    new SimpleGrantedAuthority("SCOPE_internal.read")));
                assertFalse(auth.getAuthorities().contains(
                    new SimpleGrantedAuthority("ROLE_INTERNAL_ADMIN")));
            })
            .verifyComplete();
    }

    @Test
    void managerRejectsBadKeyAndErasesRawCredential() {
        var request = CustomAuthApplication
            .InternalKeyAuthenticationToken.unauthenticated(
                "wrong-key-for-this-demo-12345");

        var manager = new CustomAuthApplication
            .InternalKeyAuthenticationManager(KEY);

        StepVerifier.create(manager.authenticate(request))
            .expectError(BadCredentialsException.class)
            .verify();

        assertNull(request.getCredentials());
        assertFalse(request.isAuthenticated());
    }

    @Test
    void managerReturnsEmptyForUnsupportedTokenType() {
        Authentication other =
            new org.springframework.security.authentication
                .UsernamePasswordAuthenticationToken(
                    "someone", "password");

        var manager = new CustomAuthApplication
            .InternalKeyAuthenticationManager(KEY);

        StepVerifier.create(manager.authenticate(other))
            .verifyComplete();
    }
}
~~~

Run:

~~~bash
gradle test
~~~

Use `./gradlew test` or `gradlew.bat test` when a wrapper is present. **Expected: 16 tests pass**, though you must run it with your local toolchain to confirm. Tests require no IdP/database. HTTP tests exercise the real WebFlux chain; standalone converter/manager tests verify the token lifecycle.

### 7.1. Limitations to Know

- `@SpringBootTest` with a public demo key does not test key entropy or a secret manager.
- Tests prove configured 200/401/403 HTTP statuses, not TLS or whether an API gateway parses headers identically to the app.
- Direct manager tests do not empirically verify constant-time timing. Digest comparison is one step, not a substitute for threat modeling.
- Tests do not prove key rotation/revocation, expiry, rate limiting, per-tenant permissions, or secret store availability.
- When upgrading Spring Security, run a regression suite covering filter order, matchers, and success/failure handlers.
- `mockAuthentication()` is useful for testing authorization in isolation, but **does not** prove Header → Converter → Manager works.

### 7.2. Negative Tests to Expand

- Revoked key, expired key, nonexistent keyId, disabled service → 401.
- Valid key for service A lacking permission for tenant B → 403/404 per policy.
- Headers containing newline/control chars, whitespace, unexpected Unicode, or exceeding 128 chars → reject.
- Gateway concatenating duplicate headers into a comma-joined value → reject.
- Internal API accidentally receiving both a Bearer JWT and an API key → explicit policy.
- Missing key on a subsequent request after a prior request succeeded → 401 (stateless).
- Monitoring/logging records no credentials; error bodies echo no raw values.
- When multiple keys operate concurrently, the manager shares no mutable global principal/authorities across calls.

## 8. Scaling to More Complex Authentication Mechanisms

### 8.1. Multiple SecurityWebFilterChains

An app may use JWT for user APIs and a custom API key for internal services:

~~~text
/api/**             -> oauth2ResourceServer.jwt()
/internal/**        -> custom AuthenticationWebFilter
/actuator/health    -> dedicated health policy
other routes        -> fallback deny
~~~

Prefer declaring `SecurityWebFilterChain` beans with explicit `securityMatcher(...)` and `@Order`. Each request uses only the **first matching chain**. For `/internal/**`, attach the custom filter only to the internal chain; the JWT chain uses the built-in resource server. Never rely on a key to bypass permissions on JWT routes.

The following structural snippet is **not a complete application**:

~~~java
@Bean
@Order(1)
SecurityWebFilterChain internal(
    ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher(
                "/internal/**"))
        .addFilterAt(keyFilter, SecurityWebFiltersOrder.AUTHENTICATION)
        .authorizeExchange(ex -> ex
            .anyExchange().hasAuthority("SCOPE_internal.read"))
        .build();
}

@Bean
@Order(2)
SecurityWebFilterChain api(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**"))
        .oauth2ResourceServer(oauth ->
            oauth.jwt(jwt -> {
                // trusted issuer/JWKS config here
            }))
        .authorizeExchange(ex -> ex
            .anyExchange().authenticated())
        .build();
}
~~~

The code above is an **illustrative snippet** assuming a preconfigured `keyFilter` variable; do not copy it into the Section 6 demo. Production needs a fallback chain for unmatched URLs; protect actuator endpoints, manage roles, CSRF, and exception handlers per chain, and ensure filters do not execute twice.

### 8.2. ReactiveAuthenticationManagerResolver

When different managers are needed per organization/issuer/tenant, `AuthenticationWebFilter` also has a constructor taking `ReactiveAuthenticationManagerResolver<ServerWebExchange>`. However, **never choose a high-privilege manager solely from an unverified `X-Tenant` header**. For multi-issuer JWTs, the framework's dedicated resolver is far more trustworthy than manual token parsing.

### 8.3. DelegatingServerAuthenticationConverter and Fallback

Spring Security provides `DelegatingServerAuthenticationConverter` for multiple converters. When supporting multiple protocols:

- Converter A returns `Mono.empty()`: no credential for A; B may try if policy allows.
- Converter A returns `Mono.error(AuthenticationException)`: credential A was sent **but invalid**; avoid accidentally falling back to a weaker mechanism.
- Two credentials present simultaneously: enforce an explicit precedence or rejection policy rather than arbitrarily accepting the first.
- Each manager handles only the token types it was designed for; never accept every Authentication and mark it true.
- Every successfully authenticated token must carry the accurate principal and authorities.

### 8.4. When to Use OAuth2/JWT/mTLS Instead of a Custom API Key?

| Mechanism | Strengths | Limitations / Assessment |
|---|---|---|
| Header API key | Simple internally, easy prototyping | Static bearer proof, weak granularity/rotation if poorly designed |
| OAuth2 client_credentials JWT | Scopes/audience, TTL, token issuance, and standard framework support | Requires managing Authorization Server, keys, policies |
| OAuth2 opaque introspection | Easy revocation via server-side state | Requires network/introspection availability |
| mTLS client certificate | Private key possession and transport identity | Requires PKI/cert lifecycle, trusted proxies |
| HMAC signed request with timestamp/nonce | Request binding, replay controls | Complex canonicalization, clock sync, nonce cache |
| Session/form login | Suited for human web users | Cookies/CSRF/session lifecycle, unlike M2M header-only |

Do not hand-roll JWT cryptographic validation inside a converter when `oauth2ResourceServer(jwt)` already exists; reserve custom Security for genuinely needed domain-specific cases.

## 9. Common Pitfalls

**1. Converter builds an authenticated Authentication:** bypasses the manager; emit only an unauthenticated candidate.

**2. Trusting `X-User` or `X-Role` from the client:** must use trusted server-side mapping, never elevate privileges from headers.

**3. Returning `Mono.empty()` for a wrong key:** can trigger unintended fallbacks; invalid credentials must fail.

**4. Returning `Mono.error(...)` for every keyless request:** public routes may falsely 401 if the matcher is broad; distinguish missing from malformed.

**5. Request token pre-populated with admin authorities:** must be empty before verification; assign authorities inside the manager.

**6. Failing to block `setAuthenticated(true)`:** other code could escalate privileges out-of-band.

**7. Double-registering the filter:** both as a global `WebFilter` bean and via `addFilterAt` causes double processing.

**8. Placing the filter after authorization:** security context is missing when rules run; use `AUTHENTICATION` order.

**9. Not configuring a matcher:** the parser runs on every endpoint and can break public routes.

**10. Leaving `anyExchange().permitAll()` on internal routes:** even with a filter, anonymous callers can still get through.

**11. Using Servlet `HttpSecurity` or `OncePerRequestFilter` on WebFlux:** reactive APIs are required.

**12. Calling `block()` or `subscribe()` inside the manager:** can deadlock/block the event loop or lose Reactor Context.

**13. Not erasing the key after verification:** raw credentials may linger in objects/traces; erase early.

**14. Logging raw keys or echoing submitted keys in errors:** data leak; use generic errors and `keyId` audits.

**15. Hardcoding secrets in source/`application.yml`:** use a secret manager/environment variables and rotation.

**16. Using short/predictable keys:** a SHA-256 digest adds no entropy; use a CSPRNG.

**17. Comparing secrets with `String.equals`:** introduces timing issues; use fixed-length digests + `MessageDigest.isEqual` or an appropriate primitive.

**18. Relying on digest checks against replay:** static API keys can still be replayed; TLS/PoP/revocation are required.

**19. Putting the key in the query string:** leaks via URLs/history/Referer/logs.

**20. Ignoring duplicate headers:** gateway and app may parse differently, creating ambiguity.

**21. Disabling CSRF in an app using browser cookies:** consider disabling only for header-only APIs with no automatic credentials.

**22. Using NoOp repository in an app needing persistent login sessions:** subsequent requests lack Authentication unless credentials are resent.

**23. Testing only with `mockAuthentication()`:** bypasses converter/manager; test real header → filter pipeline.

**24. Testing only the 200 happy path:** also test 401/403, missing/duplicate/malformed, non-matching paths, and secret revocation.

**25. Returning 401 when missing admin authority despite a valid key:** Authentication succeeded; lacking permission should return 403.

**26. Static keys in SPA/browser code:** impossible to hide from the bundle; use OIDC/PKCE/BFF.

**27. Granting all permissions to every key:** scope principals, tenants, and granted authorities per key with least privilege.

**28. No key lifecycle:** production needs issuance, rotation, expiry, revocation, auditing, and monitoring.

## 10. Production Review Checklist

1. Is there a clear technical reason to build a custom mechanism rather than built-in Basic/JWT/OAuth2/mTLS?
2. Does the converter only parse HTTP without verifying secrets or setting authenticated true?
3. Missing → empty, malformed/duplicate → `AuthenticationException`, valid format → unauthenticated token?
4. Are key format/rate/size bounded, rejecting multiple headers or control characters?
5. Does the unauthenticated token have empty authorities and the candidate credential?
6. Is `setAuthenticated(true)` blocked for callers, with only the trusted manager granting identity?
7. Does the manager accept only its own token type with proper error semantics?
8. Does the secret have sufficient entropy, provisioning via secret manager, rotation/revocation/expiry?
9. Are credentials kept out of query strings, logs, errors, metrics, and traces?
10. Do comparisons and trusted key lookups avoid unnecessary timing leaks?
11. Is the filter registered exactly once in the right `SecurityWebFilterChain`?
12. Does the matcher restrict which endpoints use this mechanism?
13. Is the filter placed at `SecurityWebFiltersOrder.AUTHENTICATION` before authorization?
14. Do private paths define explicit authority/role rules with fallback deny?
15. Do missing/invalid credentials return 401 and insufficient permissions return 403?
16. Do successful requests expose the principal in Reactor Context without persisting sessions if stateless?
17. Does CSRF configuration match the cookie/session model rather than being unconditionally disabled?
18. Is there zero blocking I/O on the Netty event loop and zero detached `subscribe()` calls?
19. Are HTTPS/mTLS/network ACLs, trusted gateway header handling, and reverse proxy policies in place?
20. For multi-tenant apps, are service principals/permissions bound server-side with resource ownership checks?
21. Do converter/manager/token unit tests and HTTP integration tests cover negative branches?
22. Do tests cover concurrency, revocation, storage outages, and rotation as appropriate for production?
23. Are framework/API packages and versions pinned, verified, and maintained with security patches?

## 11. Self-Assessment Questions

**1.** Why must the converter never call `setAuthenticated(true)`?

**Answer:** Because the converter only sees untrusted HTTP input; only the manager verifies the secret and produces an authenticated result.

**2.** Is `Mono.empty()` in a converter "authenticated anonymously" or "no attempt"?

**Answer:** It means **no authentication attempt** for this filter; the security chain can still reject private requests.

**3.** When a credential is present but malformed or duplicated, what should be returned?

**Answer:** `Mono.error(BadCredentialsException)` so the failure handler returns 401.

**4.** Should the manager assign authorities from `X-Role`?

**Answer:** No. Authorities must come from server-side policy/identity after verification.

**5.** Why are both a matcher and `authorizeExchange` needed?

**Answer:** The matcher limits *where credentials are parsed/verified*; `authorizeExchange` decides *who may call an endpoint*.

**6.** Does a NoOp security context make the principal vanish within the current request?

**Answer:** No. It only avoids persisting across requests; Authentication still lives in the current request's Reactor Context.

**7.** What response is expected when the key is valid but lacks admin authority?

**Answer:** 403 Forbidden; Authentication succeeded, but authorization lacks permission.

**8.** Can the converter be tested solely with `mockAuthentication()`?

**Answer:** No. Mocking bypasses the converter; you need converter unit tests and HTTP integration tests sending real credential headers.

**9.** Why can a key embedded in browser JavaScript never be considered secret?

**Answer:** Users can inspect the bundle/DevTools and extract the key; use OAuth2/OIDC/PKCE or a backend session instead of a static shared secret.

**10.** Why does a static key still carry replay risk even with constant-time hash comparison?

**Answer:** Digest comparison only checks credential equality; anyone who obtains the raw key can replay it until it is revoked or expires.

**11.** Do you need custom classes when using standard Bearer JWTs?

**Answer:** Usually no; use Spring Security OAuth2 Resource Server to get standard signature/issuer/expiry/audience validation.

**12.** What does it mean when a manager returns `Mono.empty()` for a different Authentication type?

**Answer:** It does not support that token type, letting the composition layer decide; it does not mean the credentials are valid.

## References

- Spring Security 6.5 — `AuthenticationWebFilter` Javadoc: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html
- Spring Security 6.5 — `ServerAuthenticationConverter` Javadoc: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authentication/ServerAuthenticationConverter.html
- Spring Security 6.5 — `ServerHttpSecurity.addFilterAt(...)` and exception handling: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security 6.5 — `SecurityWebFiltersOrder`: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/config/web/server/SecurityWebFiltersOrder.html
- Spring Security 6.5 — WebFlux Security: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security 6.5 — Authorize ServerHttpRequest: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html
- Spring Security 6.5 — Testing Authentication: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html
- Spring Security 6.5 — `ServerAuthenticationEntryPointFailureHandler`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationEntryPointFailureHandler.html
- Spring Security — `HttpStatusServerEntryPoint`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/HttpStatusServerEntryPoint.html
- OWASP Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP REST Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html
