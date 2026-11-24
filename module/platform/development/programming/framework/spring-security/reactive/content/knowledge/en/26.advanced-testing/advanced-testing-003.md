# Testing ReactiveAuthenticationManager and ServerAuthenticationConverter

## 1. Goal and context

This lesson belongs to the **Advanced Testing** section of the **Spring Security - reactive** module. In Spring WebFlux, a custom authentication mechanism typically consists of two components with distinct responsibilities:

- **`ServerAuthenticationConverter`**: reads `ServerWebExchange`, extracts credentials from the HTTP request, and creates an **unauthenticated** `Authentication` object.
- **`ReactiveAuthenticationManager`**: receives that object, calls a reactive service/repository to verify the credentials, and emits an authenticated `Authentication` or an appropriate error.

`AuthenticationWebFilter` wires the converter and manager into **`SecurityWebFilterChain`**. Proper testing requires separating each contract's tests from integrated HTTP tests, rather than just sending a few requests with `mockUser()` and concluding that the authentication mechanism works.

After this lesson, you will be able to:

1. Explain the exact three branches of `ReactiveAuthenticationManager.authenticate(...)`: **`Mono.just(Authentication)` on success**, **`Mono.empty()` when the token type is unknown/unsupported**, and **`Mono.error(AuthenticationException)` when authentication fails**.
2. Explain `ServerAuthenticationConverter.convert(...)`: missing header → `Mono.empty()`; structurally valid header → create an **unauthenticated Authentication**; duplicate, oversized, or clearly invalid header → authentication error.
3. Use **`StepVerifier`** to assert `onNext/onComplete/onError` signals, distinguish `Mono.empty()` from `Mono.error()`, and verify **deferred execution**.
4. Use **`MockServerHttpRequest`** and **`MockServerWebExchange`** to test the converter without starting an HTTP server or Spring Boot.
5. Use a fake `ReactiveKeyRepository` and `Clock.fixed(...)` to test the manager **without sleeping** or needing a real database/Redis.
6. Write **`WebTestClient.bindToApplicationContext(context).apply(springSecurity())`** tests to verify converter → manager → filter → authorization without mocking authentication.
7. Distinguish **401** due to missing/invalid credentials, **403** due to valid authentication lacking permissions, and **200** on success; confirm no authentication state carries over from a previous request.
8. Use a demo API key consisting of a key ID + random secret, store the **SHA-256 digest** of the secret, use `MessageDigest.isEqual`, and understand the limitations of a single-JVM demo.
9. Structure tests at the right levels: unit, HTTP integration, infrastructure failure, security regression, performance, and E2E; avoid false positives from `mockUser()` or `mockJwt()`.
10. Know common mistakes, log/test-fixture security, virtual time, reactive I/O, timeouts, cancellation, and multi-instance consistency.

**Scope:** This is an **advanced testing** lesson on two Spring Security reactive contracts. The API key is simply an **illustrative context** simple enough to write standalone tests; this is not a guide for building a complete production API key provisioning/rotation system. All code and tests use **Java 17+, Spring Boot 3.3.5, Spring Security 6.3.x, JUnit 5, Reactor Test**. The test results at the end of the lesson are **expected from the code** and do not claim that Gradle was executed in the current environment.

## 2. Placing the three contracts in their proper roles

An API request:

```http
GET /api/items HTTP/1.1
Host: localhost:8080
X-API-Key: ak_demo_<random-base64url-secret>
```

The string `<random-base64url-secret>` is only a placeholder. Never use this literal value as a real key.

The right flow:

```text
HTTP Request
   |
   v
SecurityWebFilterChain
   |
   v
AuthenticationWebFilter
   |
   +--> requiresAuthenticationMatcher("/api/**")?
   |      no  --> continue filter chain
   |      yes
   |       |
   |       v
   |    ServerAuthenticationConverter
   |       | 
   |       +--> missing header ........... Mono.empty()
   |       +--> invalid header ........... Mono.error(...)
   |       +--> header present ........... Authentication(false)
   |                                          |
   |                                          v
   |                              ReactiveAuthenticationManager
   |                                          |
   |                          +---------------+----------------+
   |                          |               |                |
   |                      valid            wrong/expired    unsupported
   |                     Mono.just(...)    Mono.error(...)   Mono.empty()
   |                          |               |                |
   |                         success        failure         no decision
   |                          |               |                |
   |                          v               v                v
   |                    SecurityContext     HTTP 401       continue chain
   |
   v
AuthorizationWebFilter
   +--> anonymous/no auth --> 401
   +--> authenticated, missing authority --> 403
   +--> authenticated, sufficient authority --> controller, 200
```

**Note:** `Mono.empty()` can appear at **two layers**, but its meaning is not identical:

| Where empty is returned | Specific meaning | What must NOT be inferred |
| --- | --- | --- |
| Converter does not see the expected header | No authentication attempt for this scheme | Request is permitted |
| Manager receives an unsupported `Authentication` type | Cannot make a decision for this token type | Credentials are authenticated |
| Repository lookup finds no key record | Data source has no matching record | Manager is allowed to return empty to filter as "fine" |
| `Mono.empty()` after manager is handling a wrong key | **Design bug** if invalid credentials should fail | May bypass the scheme's 401 or confuse the flow |

Once a manager accepts responsibility for handling an API key, **a wrong/disabled/expired key must be an authentication failure**. It must never construct an `Authentication` with `isAuthenticated=true` before validating credentials.

### Real interfaces

```java
@FunctionalInterface
public interface ReactiveAuthenticationManager {
    Mono<Authentication> authenticate(Authentication authentication);
}

@FunctionalInterface
public interface ServerAuthenticationConverter {
    Mono<Authentication> convert(ServerWebExchange exchange);
}
```

These are **API shape excerpts for studying the contracts**, not two interfaces to create yourself in the project. They are already provided by `spring-security-core` and `spring-security-web`.

Test assertions must verify the exact **reactive signals**:

```java
// Success: exactly one Authentication then onComplete.
StepVerifier.create(manager.authenticate(candidate))
        .assertNext(auth -> assertTrue(auth.isAuthenticated()))
        .verifyComplete();

// Unsupported type: no onNext, no error.
StepVerifier.create(manager.authenticate(unsupported))
        .verifyComplete();

// Wrong credential: onError, not onComplete.
StepVerifier.create(manager.authenticate(wrongKey))
        .expectError(BadCredentialsException.class)
        .verify();
```

These snippets are **fragments** using variables from specific test cases. The full runnable test suite appears below.

## 3. Why three test layers are needed

| Layer | Direct call | What it verifies | What it does NOT prove by itself |
| --- | --- | --- | --- |
| Converter unit test | `convert(exchange)` | Absent/duplicate/malformed header, unauthenticated token | Hash lookup, database, HTTP authorization |
| Manager unit test | `authenticate(authentication)` | Repository, hash comparison, status, authorities, Mono contract, error propagation | HTTP header parser, filter ordering |
| HTTP integration | `WebTestClient` sending real `X-API-Key` through filter chain | Converter → manager → SecurityContext → 200/401/403 | TLS/proxy/real multi-instance store |
| Persistence integration | Real R2DBC/Redis or Testcontainers | Lookup/expiry/revocation consistency, connection failure | Framework HTTP policy if bypassing chain |
| Deployment E2E | Real HTTP/TLS/proxy/client | Gateway header forwarding, timeouts, certificates, operational behavior | Any business authorization not covered by tests |

**Important:** Using `mockUser()`/`mockAuthentication()` to test **authorization** is valid, but they **bypass the manager and converter**. You cannot use a passing mock-principal test to claim password checking, token signature verification, or API key verification has been tested. The HTTP integration suite here **intentionally avoids `mockUser()`**.

### Why is `StepVerifier` better than `block()` in tests?

- Makes `onNext`, `onComplete`, and `onError` explicit.
- Distinguishes **`Mono.empty()`** from **`Mono.error()`**.
- Lets you use `assertNext(...)` to check principal, scopes, and credential erasure.
- Lets you verify subscription timing and prevent eager repository calls.
- Supports `withVirtualTime(...)` for sources using Reactor timers/schedulers without `Thread.sleep`.
- In real I/O tests, sets a **timeout** so CI never hangs indefinitely.

For reactive APIs, **do not write**:

```java
// ANTI-PATTERN: block() can hide reactive errors and hang tests.
Authentication result = manager.authenticate(candidate).block();
assertTrue(result.isAuthenticated());
```

This does not clearly verify `Mono.empty` vs `onError` and ignores reactive pipeline timing constraints. `StepVerifier` is the right tool.

## 4. Designing an API key fixture for testing

The sample uses the key format:

```text
ak_<keyId>_<base64url(32 random bytes)>
```

For example:
- `keyId=demo`: public identifier used for lookup.
- Secret part: **32 bytes** generated by `SecureRandom`, unpadded Base64URL, **43 characters** long.
- The repository stores only the **SHA-256 digest of the secret** plus metadata such as client ID, scopes, enabled, and expiresAt.
- `ServerAuthenticationConverter` turns the raw header into an unauthenticated `ApiKeyAuthenticationToken.request(raw)`.
- `ReactiveAuthenticationManager` parses the key, reads the repository, compares digests with `MessageDigest.isEqual`, checks expiry/status, and returns an authenticated token with null credentials.

In **unit tests**, you can use `new byte[32]` to build a **deterministic fixture**. That is an all-zero byte sequence with **0 entropy** and must **never be used as a real API key**. Running the demo app outside tests requires a key randomly generated by `SecureRandom` and supplied via an environment variable.

### Scenarios that must be tested

**Converter:**
- Missing `X-API-Key` → `Mono.empty()`.
- Valid header → exactly one unauthenticated token.
- Empty, oversized, comma-containing, or duplicate header → `BadCredentialsException`.
- Lowercase header name `x-api-key` is still read (HTTP header names are case-insensitive).
- Converter **does not grant roles/authorities itself**.

**Manager:**
- Valid key → authenticated principal, server-side authorities, credentials cleared.
- Same key ID with wrong secret → error.
- Non-existent key ID → error, not empty.
- Malformed key → error.
- Disabled or expired record → error.
- Manager receives `UsernamePasswordAuthenticationToken` → `Mono.empty()` because unsupported.
- Repository outage → **error is propagated**, not fail-open.
- Lookup does not run before subscription.
- At/past expiry boundary with `Clock.fixed` → accurate denial, no sleep.

**HTTP:**
- Public route anonymous → 200.
- Private route without key → 401.
- Invalid/duplicate/unknown key → 401.
- Correct key + correct scope → 200.
- Correct key + missing scope → 403.
- Next request without key → 401, no session inherited.
- Undeclared route → denied by default.

## 5. Java 17 / Spring Boot 3.3.5 project

Create the directory structure:

```text
reactive-authn-testing/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/dev/example/authntest/
    │   │   ├── AuthenticationTestingApplication.java
    │   │   ├── ApiKeyMaterial.java
    │   │   ├── ApiKeyAuthenticationToken.java
    │   │   ├── ApiKeyRecord.java
    │   │   ├── ReactiveKeyRepository.java
    │   │   ├── DemoKeyRepository.java
    │   │   ├── ApiKeyReactiveAuthenticationManager.java
    │   │   ├── ApiKeyHeaderConverter.java
    │   │   ├── SecurityConfig.java
    │   │   ├── DemoController.java
    │   │   └── LocalKeyGenerator.java
    │   └── resources/application.yml
    └── test/java/dev/example/authntest/
        ├── ApiKeyHeaderConverterTests.java
        ├── ApiKeyReactiveAuthenticationManagerTests.java
        └── ApiKeyHttpTests.java
```

Package names, class names, and source file paths match. Each Java source block below is the **complete content of a file**, not pseudocode.

### 5.1. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'reactive-authn-testing'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
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

**Why is each dependency needed?**
- `spring-boot-starter-webflux`: Reactor/Netty, reactive controllers, WebTestClient-capable WebFlux stack.
- `spring-boot-starter-security`: `ReactiveAuthenticationManager`, `AuthenticationWebFilter`, security context, and authorization.
- `spring-boot-starter-test`: JUnit Jupiter, Spring Test, mock `ServerWebExchange`, WebTestClient.
- `spring-security-test`: `springSecurity()` for WebTestClient and mutators when needed.
- `reactor-test`: `StepVerifier` and virtual-time tools.

**Do not add `spring-boot-starter-web` to a pure WebFlux project**: when both MVC and WebFlux starters are present, Spring Boot typically selects the Servlet/MVC stack, which is incompatible with this project.

### 5.2. Runtime property

`src/main/resources/application.yml`:

```yaml
server:
  port: 8080

demo:
  api-key: "${DEMO_API_KEY:}"
```

The application requires the `DEMO_API_KEY` environment variable. If missing, `DemoKeyRepository` fails to initialize (fail fast). This is **intentional**: never fall back to a dangerous default secret.

In HTTP tests, `@DynamicPropertySource` overrides `demo.api-key` with a test fixture so **no real environment variable is needed**. Unit tests do not load a Spring Boot context.

### 5.3. Main class

`src/main/java/dev/example/authntest/AuthenticationTestingApplication.java`:

```java
package dev.example.authntest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthenticationTestingApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthenticationTestingApplication.class, args);
    }
}
```

### 5.4. Key parser and digest helper

`src/main/java/dev/example/authntest/ApiKeyMaterial.java`:

```java
package dev.example.authntest;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Base64;
import java.util.HexFormat;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.springframework.security.authentication.BadCredentialsException;

public final class ApiKeyMaterial {

    private static final Pattern FORMAT = Pattern.compile(
            "^ak_([A-Za-z0-9-]{1,32})_([A-Za-z0-9_-]{43})$");

    private ApiKeyMaterial() {
    }

    public record Parts(String keyId, byte[] secret) {

        public Parts {
            secret = secret.clone();
        }

        @Override
        public byte[] secret() {
            return secret.clone();
        }
    }

    public static Parts parse(String raw) {
        if (raw == null || raw.length() > 128) {
            throw new BadCredentialsException("Invalid API key");
        }

        Matcher matcher = FORMAT.matcher(raw);
        if (!matcher.matches()) {
            throw new BadCredentialsException("Invalid API key");
        }

        byte[] decoded;
        try {
            decoded = Base64.getUrlDecoder()
                    .decode(matcher.group(2));
        } catch (IllegalArgumentException ex) {
            throw new BadCredentialsException("Invalid API key");
        }

        if (decoded.length != 32) {
            throw new BadCredentialsException("Invalid API key");
        }

        // Require canonical Base64URL without padding.
        String encoded = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(decoded);

        if (!encoded.equals(matcher.group(2))) {
            throw new BadCredentialsException("Invalid API key");
        }

        return new Parts(matcher.group(1), decoded);
    }

    public static byte[] sha256(byte[] secret) {
        try {
            return MessageDigest.getInstance("SHA-256")
                    .digest(secret);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(
                    "SHA-256 is not available", ex);
        }
    }

    public static String sha256Hex(byte[] secret) {
        return HexFormat.of().formatHex(sha256(secret));
    }
}
```

**Design rationale:** The API key has **256 random bits**, so a SHA-256 digest can serve as a verifier; **this is not a recipe for storing human passwords**. Low-entropy passwords must use an appropriate password hash such as Argon2/bcrypt/scrypt. The raw key should only be issued **once** and kept out of source/config repositories, logs, and test reports.

In production, you may use HMAC-SHA-256 with a server-side pepper to limit impact if verifier DB rows leak, provided the pepper is managed via KMS/secret manager with a rotation plan. A digest is not encryption.

### 5.5. Custom Authentication token

`src/main/java/dev/example/authntest/ApiKeyAuthenticationToken.java`:

```java
package dev.example.authntest;

import java.util.Collection;
import java.util.List;

import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;

public final class ApiKeyAuthenticationToken
        extends AbstractAuthenticationToken {

    private final String principal;
    private String credentials;

    private ApiKeyAuthenticationToken(
            String principal,
            String credentials,
            Collection<? extends GrantedAuthority> authorities,
            boolean authenticated) {

        super(authorities);
        this.principal = principal;
        this.credentials = credentials;
        super.setAuthenticated(authenticated);
    }

    public static ApiKeyAuthenticationToken request(String rawKey) {
        return new ApiKeyAuthenticationToken(
                "unverified", rawKey, List.of(), false);
    }

    public static ApiKeyAuthenticationToken verified(
            String clientId,
            Collection<? extends GrantedAuthority> authorities) {

        return new ApiKeyAuthenticationToken(
                clientId, null, authorities, true);
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
        credentials = null;
        super.eraseCredentials();
    }

    @Override
    public void setAuthenticated(boolean value) {
        if (value) {
            throw new IllegalArgumentException(
                    "Use verified(...) only after validation");
        }
        super.setAuthenticated(false);
    }
}
```

**Tests must check both states:**

| Condition | `request(rawKey)` | `verified(clientId, authorities)` |
| --- | --- | --- |
| `isAuthenticated()` | false | true |
| Principal | "unverified" (untrusted) | Client ID from repository |
| Credentials | Temporary raw key | null |
| Authorities | Empty | Server-granted list |
| Who creates it? | Converter | Manager after verification |

The private constructor along with the `verified(...)` factory and blocking `setAuthenticated(true)` prevents code outside the manager from promoting a request token to authenticated without verification.

**Never place raw credentials into principal or authorities**. `Authentication` can propagate through the reactive context; treat it as sensitive data and never log the full object.

### 5.6. Record and reactive repository

`src/main/java/dev/example/authntest/ApiKeyRecord.java`:

```java
package dev.example.authntest;

import java.time.Instant;
import java.util.Set;

public record ApiKeyRecord(
        String keyId,
        String clientId,
        String digestHex,
        Set<String> scopes,
        boolean enabled,
        Instant expiresAt) {

    public ApiKeyRecord {
        scopes = Set.copyOf(scopes);
    }
}
```

`src/main/java/dev/example/authntest/ReactiveKeyRepository.java`:

```java
package dev.example.authntest;

import reactor.core.publisher.Mono;

@FunctionalInterface
public interface ReactiveKeyRepository {
    Mono<ApiKeyRecord> findById(String keyId);
}
```

`ReactiveKeyRepository` is an abstraction defined by the example. In production, implement it with **R2DBC/reactive Redis/WebClient** or a real client that never blocks the event loop. In tests, it can be a lambda returning `Mono.just`, `Mono.empty`, `Mono.error`, or `Mono.delay`.

### 5.7. Single-JVM demo repository

`src/main/java/dev/example/authntest/DemoKeyRepository.java`:

```java
package dev.example.authntest;

import java.time.Instant;
import java.util.Map;
import java.util.Set;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Repository;

import reactor.core.publisher.Mono;

@Repository
public final class DemoKeyRepository
        implements ReactiveKeyRepository {

    private final Map<String, ApiKeyRecord> records;

    public DemoKeyRepository(
            @Value("${demo.api-key}") String rawDemoKey) {

        ApiKeyMaterial.Parts key =
                ApiKeyMaterial.parse(rawDemoKey);

        ApiKeyRecord record = new ApiKeyRecord(
                key.keyId(),
                "demo-client",
                ApiKeyMaterial.sha256Hex(key.secret()),
                Set.of("items:read"),
                true,
                Instant.MAX);

        records = Map.of(record.keyId(), record);
    }

    @Override
    public Mono<ApiKeyRecord> findById(String keyId) {
        return Mono.justOrEmpty(records.get(keyId));
    }
}
```

**Intentional demo limitations:**
- The raw key is read **once from the environment** at startup, after which only the digest is stored in the map.
- Only one client `demo-client` with scope `items:read` exists, without `items:write`.
- `Instant.MAX` is used for local demonstration, **not a valid key expiration policy for production**.
- No provisioning API, revocation, auditing, rate limiting, or multiple keys.
- Each JVM holds independent state; multi-replica deployments cannot use this in-memory map.
- Repository errors (when backed by DB/Redis) must travel as error signals and never be turned into allow.

### 5.8. Real ReactiveAuthenticationManager

`src/main/java/dev/example/authntest/ApiKeyReactiveAuthenticationManager.java`:

```java
package dev.example.authntest;

import java.security.MessageDigest;
import java.time.Clock;
import java.util.HexFormat;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public final class ApiKeyReactiveAuthenticationManager
        implements ReactiveAuthenticationManager {

    private final ReactiveKeyRepository repository;
    private final Clock clock;

    public ApiKeyReactiveAuthenticationManager(
            ReactiveKeyRepository repository, Clock clock) {
        this.repository = repository;
        this.clock = clock;
    }

    @Override
    public Mono<Authentication> authenticate(
            Authentication candidate) {

        if (!(candidate instanceof ApiKeyAuthenticationToken token)
                || token.isAuthenticated()) {
            return Mono.empty(); // Does not handle this type.
        }

        return Mono.defer(() -> {
            ApiKeyMaterial.Parts presented =
                    ApiKeyMaterial.parse(
                            (String) token.getCredentials());

            byte[] actualDigest =
                    ApiKeyMaterial.sha256(presented.secret());

            return repository.findById(presented.keyId())
                    .switchIfEmpty(Mono.error(
                            new BadCredentialsException(
                                    "Invalid API key")))
                    .flatMap(record -> {
                        byte[] expectedDigest = HexFormat.of()
                                .parseHex(record.digestHex());

                        boolean matches = MessageDigest.isEqual(
                                expectedDigest, actualDigest);

                        boolean active = record.enabled()
                                && clock.instant().isBefore(
                                        record.expiresAt());

                        if (!record.keyId().equals(presented.keyId())
                                || !matches || !active) {
                            return Mono.<Authentication>error(
                                    new BadCredentialsException(
                                            "Invalid API key"));
                        }

                        var authorities = record.scopes().stream()
                                .map(scope ->
                                        new SimpleGrantedAuthority(
                                                "SCOPE_" + scope))
                                .toList();

                        return Mono.<Authentication>just(
                                ApiKeyAuthenticationToken.verified(
                                        record.clientId(),
                                        authorities));
                    });
        });
    }
}
```

**Mandatory test points:**
1. `candidate instanceof ApiKeyAuthenticationToken` and `!isAuthenticated()`: the manager handles only the type it supports.
2. `Mono.defer(...)`: parse/hash/repository lookup run **on subscription**, not immediately when the method is called. A test can attach an `AtomicInteger` to the repository to verify.
3. `ApiKeyMaterial.parse(...)` can emit `BadCredentialsException` if malformed.
4. `repository.findById(...)` returns `Mono.empty()` for a missing record, which the manager converts into `Mono.error(BadCredentialsException)` via `switchIfEmpty`.
5. The SHA-256 digest of the raw secret is compared against the server-side digest using `MessageDigest.isEqual`, never comparing raw strings directly.
6. `clock.instant().isBefore(record.expiresAt())`: active right before expiry, **already invalid at the exact expiry instant**. Inject `Clock` to test the boundary deterministically.
7. Scopes come from the trusted record and convert to `SCOPE_items:read`; **scopes are never read from HTTP headers**.
8. Verified authentication has principal `demo-client`, credentials `null`, and `isAuthenticated=true`.
9. Store errors are propagated; never `onErrorResume(e -> Mono.just(verified))`.
10. Corrupt digests must never be silently accepted: parse errors from trusted storage become internal errors requiring monitoring/fail-closed behavior.
11. This code uses an in-memory repository without blocking I/O. When swapping stores, use a reactive driver; **never call synchronous JDBC or `.block()` on the Netty event loop**.

**Security limitations:** Constant-time digest comparison does not eliminate all timing side channels (for example, a missing key ID has a different lookup path). Production needs rate limiting, generic 401s, key enumeration protection, expiration, revocation, telemetry, and a store-outage policy.

### 5.9. Real ServerAuthenticationConverter

`src/main/java/dev/example/authntest/ApiKeyHeaderConverter.java`:

```java
package dev.example.authntest;

import java.util.List;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.server.authentication.ServerAuthenticationConverter;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

public final class ApiKeyHeaderConverter
        implements ServerAuthenticationConverter {

    private static final String HEADER = "X-API-Key";

    @Override
    public Mono<Authentication> convert(ServerWebExchange exchange) {

        List<String> values =
                exchange.getRequest().getHeaders().get(HEADER);

        if (values == null || values.isEmpty()) {
            // Missing credential: this scheme does not attempt authentication.
            return Mono.empty();
        }

        if (values.size() != 1) {
            return Mono.error(new BadCredentialsException(
                    "Invalid API key"));
        }

        String raw = values.get(0);

        if (raw == null || raw.isBlank()
                || raw.length() > 128
                || raw.indexOf(',') >= 0
                || !raw.startsWith("ak_")) {
            return Mono.error(new BadCredentialsException(
                    "Invalid API key"));
        }

        // Still an unauthenticated Authentication.
        return Mono.just(ApiKeyAuthenticationToken.request(raw));
    }
}
```

**Converter responsibility stops at the HTTP boundary:**
- Knows nothing about passwords/digests/repositories; never grants a trusted principal.
- Absent header returns empty; private routes must ultimately be denied by authorization.
- Duplicate, empty, oversized, comma-merged, or wrong-scheme headers return a generic error.
- Headers starting with `ak_` but having the wrong secret length/base64 will be rejected by the **manager** during parsing; the converter is not the entire security check.
- HTTP header names are case-insensitive, while **credential values are case-sensitive**.
- Do not accept secrets from query URLs or cookies to avoid log/history/referrer leakage.
- Never place the header in logs, metrics labels, or test failure messages.

### 5.10. WebFlux security chain: wiring converter and manager

`src/main/java/dev/example/authntest/SecurityConfig.java`:

```java
package dev.example.authntest;

import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.AuthenticationWebFilter;
import org.springframework.security.web.server.authentication.HttpStatusServerEntryPoint;
import org.springframework.security.web.server.authentication.ServerAuthenticationEntryPointFailureHandler;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ApiKeyReactiveAuthenticationManager manager) {

        var noSession =
                NoOpServerSecurityContextRepository.getInstance();
        var unauthorized =
                new HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED);

        AuthenticationWebFilter apiKeyFilter =
                new AuthenticationWebFilter(manager);

        apiKeyFilter.setRequiresAuthenticationMatcher(
                ServerWebExchangeMatchers.pathMatchers("/api/**"));

        apiKeyFilter.setServerAuthenticationConverter(
                new ApiKeyHeaderConverter());

        apiKeyFilter.setSecurityContextRepository(noSession);

        apiKeyFilter.setAuthenticationFailureHandler(
                new ServerAuthenticationEntryPointFailureHandler(
                        unauthorized));

        return http
                .securityContextRepository(noSession)
                .csrf(csrf -> csrf.disable())
                .httpBasic(basic -> basic.disable())
                .formLogin(form -> form.disable())
                .logout(logout -> logout.disable())
                .exceptionHandling(exceptions -> exceptions
                        .authenticationEntryPoint(unauthorized)
                        .accessDeniedHandler((exchange, error) -> {
                            exchange.getResponse()
                                    .setStatusCode(HttpStatus.FORBIDDEN);
                            return exchange.getResponse().setComplete();
                        }))
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/items")
                            .hasAuthority("SCOPE_items:read")
                        .pathMatchers(HttpMethod.POST, "/api/admin")
                            .hasAuthority("SCOPE_items:write")
                        .pathMatchers(HttpMethod.GET, "/api/me")
                            .authenticated()
                        .anyExchange().denyAll())
                .addFilterAt(
                        apiKeyFilter,
                        SecurityWebFiltersOrder.AUTHENTICATION)
                .build();
    }
}
```

**Configuration explanation:**
- `AuthenticationWebFilter` invokes the converter/manager; **`authenticationManager(...)` on `ServerHttpSecurity` alone will not recognize `X-API-Key`**.
- `SecurityWebFiltersOrder.AUTHENTICATION` ensures the filter runs before authorization.
- `setRequiresAuthenticationMatcher("/api/**")` only attempts API key auth on private API routes; `/public` will not fail due to an unusual header value.
- `NoOpServerSecurityContextRepository` on both the filter and HTTP chain avoids storing authentication in a session. Every new request must present an API key.
- The filter's failure handler returns **401** for invalid credentials. The entry point returns **401** when credentials are missing, while the access denied handler returns **403** for an authenticated principal missing a scope.
- `hasAuthority("SCOPE_items:read")` requires the actual authority granted by the manager. The demo only grants read, so POST `/api/admin` always returns 403 with the demo key.
- `anyExchange().denyAll()` blocks undeclared routes before reaching any controller.
- HTTP Basic/form login/logout are disabled so other authentication mechanisms cannot interfere with test results.
- **`csrf.disable()` applies only because the demo is header-only stateless API key auth without browser cookie/session credentials.** Do not copy this setting to browser/OIDC login apps with automatic cookies; threat-model CSRF and split filter chains when needed.
- This is a **real** application `SecurityWebFilterChain`, not a fake security config in tests. HTTP tests use this exact chain.

### 5.11. Controller to observe 200 and 403

`src/main/java/dev/example/authntest/DemoController.java`:

```java
package dev.example.authntest;

import java.security.Principal;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping("/public")
    public Mono<String> publicRoute() {
        return Mono.just("public-ok");
    }

    @GetMapping("/api/me")
    public Mono<String> me(Principal principal) {
        return Mono.just(principal.getName());
    }

    @GetMapping("/api/items")
    public Mono<Map<String, String>> items(Principal principal) {
        return Mono.just(Map.of(
                "client", principal.getName(),
                "result", "items-read-ok"));
    }

    @PostMapping("/api/admin")
    public Mono<String> admin() {
        return Mono.just("admin-ok");
    }
}
```

**Why is this a useful HTTP fixture?**
- `/public` lets you test that the filter matcher does not accidentally guard public routes.
- `/api/me` observes the real authenticated principal (`demo-client`).
- `/api/items` requires read authority, testing authn + authz + response body together.
- `/api/admin` requires write authority, distinguishing **403** from **401**.
- If the controller returns principal `unverified` or the key secret, that is an authentication pipeline bug; unit + HTTP tests catch incorrect principals.
- Never call `.block()` or manually construct ThreadLocal authentication in a reactive controller.

### 5.12. Generating a local key with SecureRandom

`src/main/java/dev/example/authntest/LocalKeyGenerator.java`:

```java
package dev.example.authntest;

import java.security.SecureRandom;
import java.util.Base64;

public final class LocalKeyGenerator {

    private LocalKeyGenerator() {
    }

    public static void main(String[] args) {
        byte[] bytes = new byte[32];
        new SecureRandom().nextBytes(bytes);

        String secret = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);

        // Only use to generate test keys.
        // Do not put raw keys into production logs or documentation.
        System.out.println("ak_demo_" + secret);
    }
}
```

Run in the project after compiling:

```bash
gradle classes
java -cp build/classes/java/main dev.example.authntest.LocalKeyGenerator
```

The generator prints a **random** test key; no concrete key is published in this article. Put the key into the `DEMO_API_KEY` environment variable of the shell/IDE running the app, and avoid committing or writing it into CI logs. For production, you need provisioning/secret management, scopes, expiry/revocation, and auditing; never reuse the single-JVM demo.

## 6. Unit testing ServerAuthenticationConverter with MockServerWebExchange

No Spring Boot, Netty, database, or security chain needed: instantiate `ApiKeyHeaderConverter` directly and mock HTTP requests with Spring Test.

File `src/test/java/dev/example/authntest/ApiKeyHeaderConverterTests.java`:

```java
package dev.example.authntest;

import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ApiKeyHeaderConverterTests {

    private static final String VALID_FORMAT =
            "ak_demo_" + "A".repeat(43);

    private final ApiKeyHeaderConverter converter =
            new ApiKeyHeaderConverter();

    private MockServerWebExchange exchange(String... keyValues) {
        MockServerHttpRequest.BaseBuilder<?> builder =
                MockServerHttpRequest.get("/api/items");

        if (keyValues.length > 0) {
            builder.header("X-API-Key", keyValues);
        }

        return MockServerWebExchange.from(builder.build());
    }

    @Test
    void noHeaderReturnsEmptyMono() {
        StepVerifier.create(converter.convert(exchange()))
                .verifyComplete();
    }

    @Test
    void existingHeaderProducesUnauthenticatedToken() {
        StepVerifier.create(
                converter.convert(exchange(VALID_FORMAT)))
                .assertNext(authentication -> {
                    assertTrue(
                            authentication instanceof ApiKeyAuthenticationToken);
                    assertFalse(authentication.isAuthenticated());
                    assertEquals("unverified", authentication.getName());
                    assertEquals(
                            VALID_FORMAT, authentication.getCredentials());
                    assertTrue(authentication.getAuthorities().isEmpty());
                })
                .verifyComplete();
    }

    @Test
    void emptyHeaderIsAuthenticationError() {
        StepVerifier.create(converter.convert(exchange("")))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void duplicateHeadersAreRejected() {
        StepVerifier.create(converter.convert(
                exchange(VALID_FORMAT, VALID_FORMAT)))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void commaJoinedHeadersAreRejected() {
        StepVerifier.create(converter.convert(
                exchange(VALID_FORMAT + "," + VALID_FORMAT)))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void nonApiKeySchemeIsRejectedEarly() {
        StepVerifier.create(converter.convert(
                exchange("Bearer not-an-api-key")))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void oversizeHeaderIsRejectedEarly() {
        StepVerifier.create(converter.convert(
                exchange("ak_" + "Z".repeat(200))))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void headerNamesAreCaseInsensitive() {
        MockServerWebExchange lowercase =
                MockServerWebExchange.from(
                        MockServerHttpRequest.get("/api/items")
                                .header("x-api-key", VALID_FORMAT)
                                .build());

        StepVerifier.create(converter.convert(lowercase))
                .assertNext(authentication ->
                        assertEquals(
                                VALID_FORMAT, authentication.getCredentials()))
                .verifyComplete();
    }
}
```

**Goals of the 8 tests:**
- **`Mono.empty`** when no header is present: `verifyComplete()` with no onNext.
- **`Mono.just`** when header is present: verifies type, `authenticated=false`, credentials hold the raw header **temporarily**, empty authorities.
- **`Mono.error`** on malformed/duplicate: verifies exact `BadCredentialsException`, never arbitrary 200 or 500.
- Header names are case-insensitive while credential values remain intact.
- Converter tests **do not** conclude the real secret is valid; even `"A".repeat(43)` is merely a well-formed string not yet validated by the manager.
- Do not mock a repository in converter tests, since a properly designed converter does not call the repository.

**Type note:** `MockServerHttpRequest.BaseBuilder<?>` is a Spring Test builder; if your IDE/project uses a version with a different generic class name, you can avoid the helper builder by constructing `MockServerWebExchange.from(MockServerHttpRequest.get(...).header(...).build())` per test. This code targets Spring Framework 6.1.x managed by Boot 3.3.

### An assertion that is easy to write wrong

```java
// WRONG: convert(...) is not authorized to mark authenticated.
StepVerifier.create(converter.convert(exchange(VALID_FORMAT)))
        .assertNext(auth -> assertTrue(auth.isAuthenticated()))
        .verifyComplete();
```

A test expecting `isAuthenticated=true` directly from the converter is an **anti-pattern**; the converter only **extracts credentials**. The authentication manager is responsible for verification.

## 7. Unit testing ReactiveAuthenticationManager with StepVerifier

Replace the real repository with a **fake reactive repository** fully controlled by the test. Use `Clock.fixed` to test exact expiration times without `Thread.sleep` or relying on the CI machine clock.

Test fixture:
- `TEST_SECRET_BYTES = new byte[32]`: **test only**, never use as a real credential.
- `KEY = "ak_demo_" + Base64URL(TEST_SECRET_BYTES)`.
- `Clock.fixed(2030-01-01T00:00:00Z, UTC)`.
- Record `demo-client`, `enabled=true`, `scope=items:read`, `expiresAt=NOW+300s`.

File `src/test/java/dev/example/authntest/ApiKeyReactiveAuthenticationManagerTests.java`:

```java
package dev.example.authntest;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Base64;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ApiKeyReactiveAuthenticationManagerTests {

    // Deterministic test fixture, NO real entropy.
    private static final byte[] TEST_BYTES = new byte[32];

    private static final String SECRET =
            Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(TEST_BYTES);

    private static final String KEY = "ak_demo_" + SECRET;

    private static final Instant NOW =
            Instant.parse("2030-01-01T00:00:00Z");

    private static final Clock NOW_CLOCK =
            Clock.fixed(NOW, ZoneOffset.UTC);

    private ApiKeyRecord record(
            boolean enabled, Instant expiresAt) {
        return new ApiKeyRecord(
                "demo",
                "demo-client",
                ApiKeyMaterial.sha256Hex(TEST_BYTES),
                Set.of("items:read"),
                enabled,
                expiresAt);
    }

    private ReactiveKeyRepository repository(ApiKeyRecord record) {
        return id -> id.equals(record.keyId())
                ? Mono.just(record) : Mono.empty();
    }

    private ApiKeyReactiveAuthenticationManager manager(
            ReactiveKeyRepository repository,
            Clock clock) {
        return new ApiKeyReactiveAuthenticationManager(
                repository, clock);
    }

    private ApiKeyReactiveAuthenticationManager activeManager() {
        return manager(
                repository(record(true, NOW.plusSeconds(300))),
                NOW_CLOCK);
    }

    @Test
    void correctKeyEmitsAuthenticatedIdentityAndServerScopes() {
        StepVerifier.create(activeManager().authenticate(
                ApiKeyAuthenticationToken.request(KEY)))
                .assertNext(authentication -> {
                    assertTrue(authentication.isAuthenticated());
                    assertEquals("demo-client",
                            authentication.getName());
                    assertNull(authentication.getCredentials());
                    assertTrue(authentication.getAuthorities().stream()
                            .anyMatch(authority ->
                                    authority.getAuthority().equals(
                                            "SCOPE_items:read")));
                    assertFalse(authentication.getAuthorities().stream()
                            .anyMatch(authority ->
                                    authority.getAuthority().equals(
                                            "SCOPE_items:write")));
                })
                .verifyComplete();
    }

    @Test
    void knownIdWithWrongSecretFailsAuthentication() {
        byte[] wrongSecret = new byte[32];
        wrongSecret[0] = 1;

        String wrongKey = "ak_demo_"
                + Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(wrongSecret);

        StepVerifier.create(activeManager().authenticate(
                ApiKeyAuthenticationToken.request(wrongKey)))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void unknownKeyIdIsAnErrorNotAnEmptyMono() {
        String unknown = "ak_unknown_" + SECRET;

        StepVerifier.create(activeManager().authenticate(
                ApiKeyAuthenticationToken.request(unknown)))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void malformedApiKeyFailsAuthentication() {
        StepVerifier.create(activeManager().authenticate(
                ApiKeyAuthenticationToken.request("not-an-api-key")))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void unsupportedAuthenticationTypeReturnsEmptyMono() {
        Authentication basic =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "user", "password");

        StepVerifier.create(activeManager().authenticate(basic))
                .verifyComplete();
    }

    @Test
    void disabledKeyFailsAuthentication() {
        var target = manager(
                repository(record(false, NOW.plusSeconds(300))),
                NOW_CLOCK);

        StepVerifier.create(target.authenticate(
                ApiKeyAuthenticationToken.request(KEY)))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void expiredKeyFailsWithoutSleeping() {
        var target = manager(
                repository(record(true, NOW.minusSeconds(1))),
                NOW_CLOCK);

        StepVerifier.create(target.authenticate(
                ApiKeyAuthenticationToken.request(KEY)))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void exactExpiryInstantFailsWithoutRace() {
        var target = manager(
                repository(record(true, NOW)),
                NOW_CLOCK);

        StepVerifier.create(target.authenticate(
                ApiKeyAuthenticationToken.request(KEY)))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void repositoryFailureIsPropagatedNotAllowed() {
        ReactiveKeyRepository unavailable =
                id -> Mono.error(new IllegalStateException(
                        "Key store unavailable"));

        var target = manager(unavailable, NOW_CLOCK);

        StepVerifier.create(target.authenticate(
                ApiKeyAuthenticationToken.request(KEY)))
                .expectError(IllegalStateException.class)
                .verify();
    }

    @Test
    void authenticationWorkIsDeferredUntilSubscription() {
        AtomicInteger lookups = new AtomicInteger();

        ReactiveKeyRepository instrumented = id -> {
            lookups.incrementAndGet();
            return Mono.just(record(true, NOW.plusSeconds(300)));
        };

        var target = manager(instrumented, NOW_CLOCK);

        Mono<Authentication> result = target.authenticate(
                ApiKeyAuthenticationToken.request(KEY));

        // Not subscribed yet -> repository not read.
        assertEquals(0, lookups.get());

        StepVerifier.create(result)
                .expectNextCount(1)
                .verifyComplete();

        assertEquals(1, lookups.get());
    }

    @Test
    void asyncRepositoryCanBeTestedWithVirtualTime() {
        ReactiveKeyRepository delayed = id ->
                Mono.delay(Duration.ofSeconds(10))
                        .thenReturn(
                                record(true, NOW.plusSeconds(300)));

        var target = manager(delayed, NOW_CLOCK);

        StepVerifier.withVirtualTime(() ->
                target.authenticate(
                        ApiKeyAuthenticationToken.request(KEY)))
                .thenAwait(Duration.ofSeconds(10))
                .assertNext(auth ->
                        assertTrue(auth.isAuthenticated()))
                .verifyComplete();
    }
}
```

### Analyzing the 11 manager tests

| Group | Test | Expected result |
| --- | --- | --- |
| Success | Correct key | Exactly one verified Authentication then complete |
| Secret validation | Same ID, wrong secret | `BadCredentialsException` |
| Missing record | Unknown ID | Error, **not** empty |
| Input validation | Malformed raw key | Error |
| Unsupported type | UsernamePasswordAuthenticationToken | **Empty Mono** |
| Status | Disabled | Error |
| Expiration | Before/at expiry boundary | Error |
| Failure propagation | Repository unavailable | `IllegalStateException`, never accepted |
| Laziness | Before subscribe | Zero repository lookups |
| Asynchronous | `Mono.delay` + virtual time | Fast test, no sleep |

**Important note:** `StepVerifier.withVirtualTime(...)` only replaces scheduling for **Reactor timers** like `Mono.delay`. It **does not advance `java.time.Clock`** used by the manager. To test expiration, inject `Clock.fixed(...)` as in the two expiration tests. Never rely on `Thread.sleep(1000)` or the system clock to test boundaries: that creates flaky tests.

**Repository error considerations:**
- `Mono.error(IllegalStateException)` from the store is not "wrong API key" in business terms; real infrastructure needs safe error mapping/monitoring.
- However, this error **must never turn into an authenticated principal**. For security APIs, silent fail-open is more dangerous than availability loss.
- Unit tests can assert the error is propagated; HTTP/E2E tests should define 5xx/503/circuit breaker behavior according to the system.

**Why do these tests not use a Spring context?** Because these are unit tests of the manager contract whose only dependencies are a fake repository and a fixed clock. They run fast and provide exact error signals. Spring Boot context tests are reserved for the filter+HTTP path in the next section.

## 8. HTTP integration tests: WebTestClient with real manager and converter

To prove that **`AuthenticationWebFilter`**, **`ServerAuthenticationConverter`**, **`ReactiveAuthenticationManager`**, and **`SecurityWebFilterChain`** work together, send a **real `X-API-Key` HTTP header** inside a mock WebFlux server:

```java
WebTestClient client = WebTestClient
        .bindToApplicationContext(context)
        .apply(springSecurity())
        .configureClient()
        .build();
```

`springSecurity()` here is the Spring Security WebFlux test configurer. **Do not use `mockUser()` in credential-checking tests**; if `mockUser` passes, it proves nothing about whether the manager verified the secret.

Test fixtures are supplied via `@DynamicPropertySource` overriding `demo.api-key` when the test Spring Boot context starts. This keeps production/demo free of insecure default keys while keeping tests deterministic.

File `src/test/java/dev/example/authntest/ApiKeyHttpTests.java`:

```java
package dev.example.authntest;

import java.util.Base64;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class ApiKeyHttpTests {

    // TEST FIXTURE ONLY: all-zero bytes have no entropy.
    private static final String SECRET =
            Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(new byte[32]);

    private static final String KEY = "ak_demo_" + SECRET;

    @DynamicPropertySource
    static void demoKeyProperty(DynamicPropertyRegistry registry) {
        registry.add("demo.api-key", () -> KEY);
    }

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
                .bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void publicRouteDoesNotRequireApiKey() {
        client.get().uri("/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("public-ok");
    }

    @Test
    void privateRouteWithoutKeyIs401() {
        client.get().uri("/api/items")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void correctKeyAndReadScopeAreAccepted() {
        client.get().uri("/api/items")
                .header("X-API-Key", KEY)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.client")
                .isEqualTo("demo-client")
                .jsonPath("$.result")
                .isEqualTo("items-read-ok");
    }

    @Test
    void principalAfterRealAuthenticationIsTrustedClientId() {
        client.get().uri("/api/me")
                .header("X-API-Key", KEY)
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("demo-client");
    }

    @Test
    void malformedHeaderReturns401() {
        client.get().uri("/api/items")
                .header("X-API-Key", "not-an-api-key")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void unknownKeyIdReturns401() {
        client.get().uri("/api/items")
                .header("X-API-Key", "ak_unknown_" + SECRET)
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void wrongSecretReturns401() {
        byte[] altered = new byte[32];
        altered[0] = 1;

        String wrongKey = "ak_demo_"
                + Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(altered);

        client.get().uri("/api/items")
                .header("X-API-Key", wrongKey)
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void duplicateHeaderValuesReturn401() {
        client.get().uri("/api/items")
                .headers(headers -> {
                    headers.add("X-API-Key", KEY);
                    headers.add("X-API-Key", KEY);
                })
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void keyCanAuthenticateButFailAuthorization() {
        client.post().uri("/api/admin")
                .header("X-API-Key", KEY)
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void authenticationIsNotRememberedOnNextRequest() {
        client.get().uri("/api/items")
                .header("X-API-Key", KEY)
                .exchange()
                .expectStatus().isOk();

        client.get().uri("/api/items")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void unknownRouteIsDeniedByDefault() {
        client.get().uri("/api/unknown")
                .header("X-API-Key", KEY)
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void publicRouteIgnoresMalformedApiKeyHeader() {
        // Filter matcher /api/** does not trigger on /public.
        client.get().uri("/public")
                .header("X-API-Key", "not-an-api-key")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("public-ok");
    }
}
```

### Why are these 12 HTTP tests valuable?

- **No authentication mocks**: to get 200, the request must pass through `ApiKeyHeaderConverter.convert`, `ApiKeyReactiveAuthenticationManager.authenticate`, repository, digest check, enabled/expiry, and authorization.
- **401 missing header**: converter returns empty, security policy requires auth.
- **401 malformed/duplicate**: converter or manager signals an error, failure handler translates to unauthorized.
- **200 valid**: principal must be the verified ID from server metadata, not the raw header.
- **403 valid but missing `SCOPE_items:write`**: proves authentication and authorization are two distinct decisions.
- **401 second request**: no authentication is saved via WebSession, so each request needs a key.
- **403 unknown path**: `anyExchange().denyAll()` prevents other routes from being implicitly exposed.
- **200 public with malformed header**: matcher only reads API keys on `/api/**`, not applying the filter to every public request.

**Limitations:** Tests run the mock WebFlux HTTP stack inside a Spring ApplicationContext, without real TLS/Netty TCP sockets or proxies. The demo repository is in-memory in one JVM and does not test concurrency or multi-replica key rotation.

### Do not "test the manager" by mocking the manager

A suite like:

```java
// ANTI-PATTERN when the goal is testing the real manager:
@MockBean
ReactiveAuthenticationManager manager;

// ... stub:
when(manager.authenticate(any()))
        .thenReturn(Mono.just(
                ApiKeyAuthenticationToken.verified(
                        "demo-client", List.of())));
// then assert HTTP 200
```

This is an **anti-pattern fragment**. It may test filter wiring, but **does not test hashing, expiry, disabled status, error propagation, or principal mapping in the real manager**. This test is useful at the **filter-only isolation** level when you intentionally want to mock the manager; never advertise it as an authentication integration test.

### Do not "test the converter" with mockUser()

```java
// ANTI-PATTERN if intending to test the X-API-Key header parser:
client.mutateWith(mockUser("admin"))
        .get().uri("/api/me")
        .exchange()
        .expectStatus().isOk();
```

`mockUser()` creates a test SecurityContext. It needs no `X-API-Key` header and does not guarantee the converter was invoked. This pattern is only appropriate for testing authorization with a simulated identity.

## 9. Running tests and interpreting results

From the `reactive-authn-testing` directory:

```bash
gradle test
```

If a Gradle Wrapper exists:

```bash
./gradlew test
```

On Windows:

```powershell
.\gradlew.bat test
```

**Expected from the code:** 
- 8 converter unit tests.
- 11 manager unit tests.
- 12 HTTP integration tests.
- **Total 31 JUnit tests**.

These are **expected test counts** from the lesson's files, not an actual Gradle execution report. When executing, inspect `build/reports/tests/test/index.html` or your IDE/CI test runner.

Key expected results:

| Request / Test | Result |
| --- | --- |
| Converter no header | `Mono.empty()` |
| Converter valid header | Exactly one `Authentication(false)` |
| Converter duplicated/malformed | `BadCredentialsException` |
| Manager unsupported type | `Mono.empty()` |
| Manager valid key | `Authentication(true)`, credentials null |
| Manager wrong/missing/disabled/expired | `BadCredentialsException` |
| Manager store outage | Error propagated, not authenticated |
| GET `/public` | 200 |
| GET `/api/items` no key | 401 |
| GET `/api/items` valid key | 200 + verified client ID |
| GET `/api/items` wrong key | 401 |
| POST `/api/admin` valid key, missing scope | 403 |
| One request valid key, next request no key | 200 then 401 |

### A minimal scenario outside JUnit

Generate a local `SecureRandom` key using `LocalKeyGenerator`, export `DEMO_API_KEY` to the environment, and run:

```bash
gradle bootRun
```

Then (on localhost only for learning):

```bash
curl -i http://localhost:8080/public

curl -i http://localhost:8080/api/items

curl -i -H "X-API-Key: $DEMO_API_KEY" \
  http://localhost:8080/api/items

curl -i -H "X-API-Key: $DEMO_API_KEY" \
  -X POST http://localhost:8080/api/admin
```

**Expected:** public 200, private without key 401, items with valid key 200, POST admin missing scope 403. On Windows PowerShell, environment variable and line-continuation syntax differ from Bash; adjust shell examples to fit your environment.

**Security note:** `curl -H "X-API-Key: ..."` can expose credentials in process listings or shell history depending on the OS; for real keys, prefer a secret-aware HTTP client or integration tests that do not log headers. Always use HTTPS/TLS in production.

## 10. Advanced StepVerifier usage and avoiding flaky tests

### 10.1. Three kinds of signal assertions

```java
// Success: exactly one value and complete.
StepVerifier.create(successMono)
        .expectNextCount(1)
        .verifyComplete();

// Not handled: no value, completes normally.
StepVerifier.create(unsupportedMono)
        .verifyComplete();

// Failure: must emit AuthenticationException.
StepVerifier.create(invalidMono)
        .expectError(BadCredentialsException.class)
        .verify();
```

These are **fragments**; `successMono`, `unsupportedMono`, and `invalidMono` are variables in specific tests. `expectNextCount(1)` only counts, while `assertNext(...)` can inspect credential cleanup/principal/authorities.

### 10.2. Timeouts for I/O tests

In tests with real Redis/R2DBC/WebClient, `StepVerifier.verify()` has no useful default timeout unless configured. You can use:

```java
StepVerifier.create(manager.authenticate(request))
        .expectNextCount(1)
        .verifyComplete();
```

The form above suits synchronous/finite Monos in fixtures. For I/O sources, consider:

```java
StepVerifier.create(manager.authenticate(request))
        .expectNextCount(1)
        .expectComplete()
        .verify(Duration.ofSeconds(3));
```

This is a **fragment requiring `Duration` import**, bounding test duration so CI does not hang. A 3-second timeout is illustrative; pick based on your actual performance envelope/CI. Never use `Thread.sleep` to wait for events in tests.

### 10.3. Virtual time is not the application clock

`Mono.delay(Duration.ofSeconds(10))` belongs to the Reactor scheduler and can be tested with `StepVerifier.withVirtualTime(...)`:

```java
StepVerifier.withVirtualTime(() ->
        manager.authenticate(candidate))
        .thenAwait(Duration.ofSeconds(10))
        .expectNextCount(1)
        .verifyComplete();
```

**However, `Clock.instant()` used by the manager will not jump 10 seconds automatically**. For expiry/lockout, inject `Clock.fixed` or a controllable clock in tests. Create `Mono.delay` inside the publisher built after virtual scheduler initialization when using complex custom scheduling.

### 10.4. Testing laziness and deferred side effects

The manager returns `Mono.defer(...)` so the lookup **does not run when the method is called**, only on subscription. The test `authenticationWorkIsDeferredUntilSubscription` uses an `AtomicInteger` in the repository:

```text
construct Mono --> lookups = 0
subscribe      --> lookups = 1
complete       --> no extra lookup
```

If a manager calls a blocking DB **before returning the Mono**, this test catches the lookup count increasing before subscription (provided the fake repository measures at the actual call site). Never write `Mono.just(repository.blockingLookup(...))`, because the argument executes eagerly at method invocation.

### 10.5. Testing specific error signals

A good regression suite does not just call generic `expectError()`; it verifies:
- `BadCredentialsException` for invalid keys.
- `Mono.empty` for unsupported authentication **types**.
- `IllegalStateException` or an appropriate error for store unavailability.
- If malformed input causes `ClassCastException`/`NullPointerException` instead of BadCredentials, the converter/manager has a bug.
- Errors are not turned into success by `onErrorResume(e -> Mono.just(verified))`.

**Do not assert that the response body always contains "unknown key id", "digest mismatch", or "disabled client"**. A generic 401 is safer for clients; internal audits can record non-secret error codes.

## 11. When to test AuthenticationWebFilter in isolation

Beyond unit and full HTTP integration tests, you sometimes want to isolate the filter itself. The following is a **guiding fragment**, not a complete Java file:

```java
AuthenticationWebFilter filter = new AuthenticationWebFilter(manager);
filter.setServerAuthenticationConverter(converter);
filter.setRequiresAuthenticationMatcher(
        ServerWebExchangeMatchers.pathMatchers("/api/**"));
filter.setSecurityContextRepository(
        NoOpServerSecurityContextRepository.getInstance());
filter.setAuthenticationFailureHandler(
        new ServerAuthenticationEntryPointFailureHandler(
                new HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED)));
```

Then testing via `MockServerWebExchange`/`WebFilterChain` can check:
- Is the converter invoked when the path matches?
- On absent credentials, is the downstream filter chain invoked?
- On invalid credentials, does the failure handler return 401?
- On valid credentials, does downstream see the authenticated principal in Reactor Context?
- When the converter emits `Mono.error`, is the manager skipped?
- When the manager returns `Mono.empty`, how does the filter behave?

**Creating a filter-only test suite is not mandatory to finish this lesson** since `WebTestClient` integration already covers real wiring, but filter-only tests are helpful when you have multiple custom matchers, authentication managers, or scheme precedence rules.

### Controlling invocation counts with a fake manager

```java
AtomicInteger invocations = new AtomicInteger();

ReactiveAuthenticationManager spyManager = request -> {
    invocations.incrementAndGet();
    return Mono.error(
            new BadCredentialsException("Invalid API key"));
};
```

This is a fragment. When the converter returns empty, manager invocations must be 0. When a header is malformed, the converter should fail before the manager. With a valid header shape, the manager is called exactly once. **Do not count creating the Mono as an HTTP request having run**: Spring Security/Reactor must subscribe to the publisher before any action occurs.

### A nuance: failure handler vs authorization entry point

Two errors can originate from different places:
- **Header present but invalid:** `AuthenticationWebFilter` invokes the authentication failure handler → HTTP 401.
- **Header absent:** converter returns empty, filter continues, `AuthorizationWebFilter` sees anonymous; `ExceptionTranslationWebFilter` invokes the authentication entry point → HTTP 401.
- **Header valid but missing scope:** authentication succeeds, then access denied handler → HTTP 403.

Therefore you must test **missing, invalid, and insufficient-scope** cases, not just one 401 request and one 200 request.

## 12. Integration testing with database/Redis and distributed failures

The in-memory demo repository makes testing the manager contract fast, but production key stores usually live in Redis/R2DBC or an auth service. When swapping the backing store, add tests for:

| Scenario | Required test | Risk if omitted |
| --- | --- | --- |
| DB record active | Manager creates principal | Wrong lookup/schema |
| Key revoked/disabled | New request returns 401 | Stale cache still says enabled |
| Key just expired | Manager returns 401 | Clock skew/stale record |
| Store returns `Mono.empty` | BadCredentials | Missing record treated as no auth attempt |
| Store timeout | Error/fail closed | Fail-open or hung request |
| Store network reset | Error/fail closed; bounded retry | Retry amplification |
| Two replicas | Same key/expiry/revocation state | Node A denies, node B allows |
| Key rotation overlap | New key accepted, old key disabled per SLA | Downtime/old key exposure |
| Quota/rate limit | Throttles abusive traffic | Brute-force/DoS |
| Concurrent requests | No SecurityContext leak between users | Cross-request identity confusion |
| Wrong tenant/resource | Access denied even with valid key | Cross-tenant IDOR |
| Gateway header rewriting | Converter receives exact `X-API-Key` | 401 at ingress or auth bypass |
| Secret redaction | Logs/APM contain no key | Credential leakage |

### Testcontainers/R2DBC when needed

An integration test can use Testcontainers to start real PostgreSQL/Redis and seed two key records:
- `demo-read` enabled, read scope;
- `demo-disabled` disabled;
- explicit expiry using a controlled `Clock`.

Then swap `ReactiveKeyRepository` for the real adapter to test query/connection behavior. When seeding keys into DB fixtures, **store the digest**, not the raw secret. These tests differ from the manager unit tests in this lesson and usually run in a CI integration suite with suitable infrastructure.

### Important note on revocation SLAs

If a key registry caches an `enabled=true` record for 5 minutes, an admin revocation will not apply immediately across all instances. You must define:
- measurement start point (revocation transaction commit),
- cache/negative-cache TTL,
- replication lag,
- maximum propagation delay,
- fail-open/fail-closed policy on store outage,
- handling of in-flight requests that authenticated before revocation.

**A manager unit test in a single JVM does not prove cluster-wide immediate revocation.**

### Reactive performance and schedulers

- A blocking JDBC repository directly inside `flatMap` can block the Netty event loop.
- Use R2DBC/reactive Redis/WebClient, connection pools, and bounded timeouts.
- If forced to use a blocking driver, isolate it with bounded `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` and monitoring; do not treat it as a universal substitute for a reactive driver at arbitrary load.
- Test timeouts/cancellation/circuit breakers; never build infinite retries into the authentication path.
- Never call `.subscribe()` ad-hoc inside a manager/filter: return the publisher so the framework manages it.

## 13. Special security practices for test fixtures and logs

### 13.1. Never put real API keys into test code

The `new byte[32]` test fixture in unit tests is **unsafe if used in production**. It only exists to produce deterministic data for assertions. Production keys must be generated with `SecureRandom`, have sufficient entropy, and be shown only once.

Use different dummy IDs/secrets between unit tests and dev/staging/prod. Never commit `.env` files containing live keys or client secrets.

### 13.2. Never log credentials on assertion failures

If an HTTP test fails:
- Do not print raw `X-API-Key`, `Authorization`, or response headers containing tokens.
- Avoid `toString()` on raw Authentication or requests in error diagnostics if they might contain credentials.
- Log sanitized key IDs if policy permits, never secrets or digests.
- Redact in CI, APM, reverse proxies, and HTTP trace collectors.
- Never let screenshots or network traces carrying bearer secrets enter public documentation.

### 13.3. Timing/constant-time comparison

`MessageDigest.isEqual` compares digest bytes while avoiding naive comparison loops. Still, lookup time for an unknown ID may differ from a known ID; response bodies/statuses must remain generic, and rate limiting plus abuse detection are necessary. Do not invent random sleeps as a security control: they can cause DoS and do not eliminate side channels.

### 13.4. When to replace a random API key hash with a password hash?

A 256-bit random API key differs from a human-chosen password. For random secrets, SHA-256/HMAC verifiers are typically appropriate when paired with storage access controls, rate limits, rotation, and breach monitoring. For **user passwords**, never use a single SHA-256 pass; use Argon2/bcrypt/scrypt per current guidance.

### 13.5. CSRF, CORS, and browsers

This demo is **machine-to-machine API key-only**, actively receiving credentials in a custom header with no browser session-cookie credentials, so disabling CSRF is conditional on that model. In hybrid browser session/OIDC apps, never disable CSRF globally just because a POST test fails.

`X-API-Key` is a custom header, so cross-origin browser requests may trigger a CORS preflight; preflight requests normally do not carry the raw API key. Requiring the key on preflight can prevent browsers from sending the real request. However, **never embed a shared server API key in a public SPA/mobile app**: users can extract it from the JS bundle/DevTools or binary.

## 14. Common testing mistakes

| Mistake | Likely cause | How to fix |
| --- | --- | --- |
| Converter returns empty on duplicate headers | Code used `getFirst` and ignored the rest | Check the `get(...)` list and reject duplicates |
| Converter marks token authenticated | Confused HTTP parsing with authentication | Request factory creates `authenticated=false` |
| Manager returns empty for wrong key | Confused "unsupported" with "invalid" | `Mono.error(BadCredentialsException)` |
| Manager returns the unauthenticated token back | Did not build a verified principal | Return authenticated only after verification |
| Manager ignores disabled/expiry | Only compared hashes | Test `enabled`, `Clock.fixed` expiry boundaries |
| Credentials remain stored after success | Verified token retained raw key | Assert `getCredentials()==null` |
| Unit test only asserts `expectNextCount(1)` | Unclear if principal/authorities are right | Use `assertNext` to inspect contents |
| Manager test calls repo before subscribe | Synchronous execution before building Mono | `Mono.defer` and counter assertions |
| Expiry test is flaky | `Instant.now()` + `Thread.sleep` | Inject `Clock.fixed`/test clock |
| Timeout test hangs CI | `StepVerifier.verify()` without explicit timeout | `verify(Duration)` in I/O tests |
| Store outage leads to 200 | `onErrorResume(...allow)` present | Fail-closed and monitor |
| HTTP 401 missing-key test never runs filter | Missing key handled by authorization entry point | Also test invalid key and valid key to cover manager |
| HTTP test uses `mockUser()` | Bypasses converter/manager | Send real `X-API-Key` header |
| HTTP test only uses `bindToController` | Missing `SecurityWebFilterChain` | Bind Spring ApplicationContext + `springSecurity()` |
| HTTP test uses `bindToServer()` with mock mutators | Mock context is not sent over TCP | Use real credentials for live HTTP |
| Missing `spring-security-test` | `springSecurity()` unavailable | Add test dependency matching Boot BOM |
| Wrong `SecurityWebFiltersOrder` | Authentication runs after authorization | Use `AUTHENTICATION` phase |
| 401 turns into 302 | Form login enabled | Disable form login for APIs or configure explicit entry point |
| 403 when valid key hits read endpoint | Scope mapping mismatch | Assert `SCOPE_items:read` and route policy |
| 403 on POST in browser app | Missing CSRF token | Keep CSRF, use `csrf()` in mock-server tests |
| Default TestWebClient has mock admin | Anonymous tests become invalid | Create fresh client per test |
| HTTP test returns 200 but wrong principal | Controller test only asserted status | Assert JSON/client identity |
| Permissions lost across replicas | In-memory map / stale key store | Shared repository and consistency tests |
| Converter accepts credential via URL query | Secret leaked in logs/referrer | Header only; redaction |
| Test traces contain raw API key | Failure logging/CI artifacts | Never log headers, rotate if leaked |
| Framework upgrade breaks types/imports | Reading docs for another version | Match Spring Security/Framework docs to BOM |

## 15. QA checklist before merging

- [ ] Test converter in isolation with `MockServerWebExchange`, no Spring Boot needed.
- [ ] Test converter **absent/valid/duplicate/oversize/malformed**.
- [ ] Converter never grants an authenticated principal or authorities.
- [ ] Test manager in isolation with `StepVerifier` and a fake reactive repository.
- [ ] Manager returns **`Mono.empty` for unsupported types**.
- [ ] Manager returns **`Mono.error` for invalid keys**.
- [ ] Manager returns **`Mono.just` verified `Authentication`** for valid keys.
- [ ] Test principal, server-side scopes, and credential erasure.
- [ ] Test disabled, expired, exact expiry, and missing records.
- [ ] Test that repository failures never turn into allow.
- [ ] Test `defer`: lookup runs only after subscription.
- [ ] If delays are used, test with Reactor virtual time; test expiry with `Clock.fixed`.
- [ ] HTTP tests go through the **real filter + converter + manager**, without `mockUser`.
- [ ] Test private without key = 401, wrong key = 401, valid read = 200, missing scope = 403.
- [ ] Test duplicate headers / unknown path / no session leakage.
- [ ] Test client built from the real ApplicationContext with `.apply(springSecurity())`.
- [ ] CSRF enabled/disabled is justified by credential type; never copy `csrf.disable()` into browser apps.
- [ ] Production logs/proxy/APM redaction covers `X-API-Key` and Authorization.
- [ ] Tests contain no production credentials or raw API keys in reports.
- [ ] Add store/Redis/R2DBC, timeout, and multi-instance revocation tests before production.
- [ ] Security code never blocks the event loop or calls `.subscribe()` ad-hoc.
- [ ] Actually inspect test reports after running Gradle; never rely solely on example code.
- [ ] Production Spring Boot/Spring Security versions are updated and supported.

## 16. Self-check questions

**1. What does `ServerAuthenticationConverter` do?**  
Converts an HTTP exchange into an unauthenticated `Mono<Authentication>` from request credentials, without checking hashes/DB.

**2. When the scheme's credential is absent, what does the converter return?**  
`Mono.empty()`, meaning no authentication attempt is made for that scheme.

**3. What if the manager does not support the input Authentication type?**  
`Mono.empty()` per contract because it makes no decision for that type.

**4. What if credentials match the manager's supported type but are wrong?**  
`Mono.error(AuthenticationException)`, such as `BadCredentialsException`.

**5. Why not return `Mono.empty()` for a wrong API key?**  
Because it can hide failures and confuse multi-manager flows; the manager must signal authentication failure.

**6. What must success assert besides `isAuthenticated()`?**  
Trusted principal, right authorities, null credentials, exactly one onNext then onComplete.

**7. How does `StepVerifier.verifyComplete()` differ from `expectError(...).verify()`?**  
One asserts error-free completion, while the other asserts a terminal error of the expected type.

**8. What can `MockServerWebExchange` test?**  
How the converter handles method/path/headers and creates `Authentication`, without an HTTP network.

**9. Why use `Clock.fixed`?**  
To test disabled/expired/boundary conditions deterministically without depending on CI timing.

**10. Does `withVirtualTime` automatically advance `Clock.instant()`?**  
No; it only controls Reactor timers/schedulers when used properly.

**11. Why is `Mono.defer` useful in the manager?**  
It ensures parsing/hashing/repository lookup run at subscribe time, avoiding blocking side effects before the publisher runs.

**12. Is testing the manager via `mockUser()` targeting the right thing?**  
No. `mockUser()` bypasses the manager/converter and only fits authorization tests.

**13. Where is `springSecurity()` used?**  
When building a mock `WebTestClient` via `bindToApplicationContext(context).apply(springSecurity()).configureClient().build()`.

**14. Why test both a missing header and a wrong header?**  
A missing header may fail at the authorization entry point, whereas a wrong header tests the converter/manager failure path.

**15. Why does a valid key missing a scope return 403?**  
Authentication succeeded, but authorization lacks the required authority.

**16. When the repository returns `Mono.empty` for an unknown ID, what should the manager do?**  
Convert it into `BadCredentialsException`; never return empty for bad credentials in this scheme.

**17. On a store timeout, should you return a verified principal to keep availability?**  
No for security APIs that must fail closed; design an explicit outage response.

**18. Why use SHA-256 instead of bcrypt in the key example?**  
Because the secret is 256 random bits, unlike low-entropy passwords. Production also needs rotation, rate limiting, and verifier protection.

**19. Why should credentials be null in a successful Authentication?**  
To reduce the risk of key exposure via context/logging/serialization.

**20. Does `NoOpServerSecurityContextRepository` guarantee every request is independent?**  
It avoids saving context in the repository; other authentication schemes or gateway state must also be considered. Test a second request with no header.

**21. How many test layers should you have?**  
Converter unit, manager unit, HTTP integration; add persistence/E2E depending on risk.

**22. When do you test with real Netty/TLS/proxy?**  
When you need to verify HTTP networking, certificates, header forwarding, cookies, or infrastructure behavior that a mock `WebTestClient` cannot prove.

### Hands-on exercises

1. Run the 8 converter tests and explain why a missing header returns empty while a malformed header errors.
2. Run the 11 manager tests, distinguish unsupported types from wrong keys, and verify null credentials after success.
3. Run the 12 HTTP tests and explain 200/401/403 across the converter/manager/authorization layers.
4. Try changing the converter to `getFirst("X-API-Key")`, observe the duplicate-header test fail, and analyze HTTP request smuggling/mismatch risks at gateways.
5. Try having the manager return `Mono.empty()` for wrong keys, and analyze the difference between the failure handler and the authorization entry point.
6. Try putting the raw credential in the verified principal, write a test catching the leak, and fix it with null credentials.
7. Try removing `.apply(springSecurity())` from the mock WebTestClient setup and observe what changes in integration tests and mutators.
8. Try using `mockUser("demo-client")` instead of the header in one test, and point out which code is no longer tested.
9. Add a disabled key record to the fake repository and assert `BadCredentialsException`.
10. Add `expiresAt` checks with `Clock.fixed` right before and at the expiry instant without `Thread.sleep`.
11. Simulate a 60s repository delay using `Mono.delay` and write a `StepVerifier.withVirtualTime` test.
12. Add a timeout limit to manager I/O and test fail-closed timeout using virtual time.
13. Add `SCOPE_items:write` to another key and test POST admin returning 200 while the read-only key returns 403.
14. Replace the demo repository with R2DBC/Redis and test that two instances both observe a revoked key.
15. Test that the converter treats header names case-insensitively while treating credential values case-sensitively.
16. Add a tenant ID to the trusted key record and test resource ownership to prevent cross-tenant IDOR.
17. Build a `bindToServer()`/`RANDOM_PORT` integration test sending a real key over HTTP and compare it with the mock client.
18. Design rate limiting, generic 401s, and log redaction to mitigate brute force and credential enumeration.
19. Verify that the gateway/proxy does not inject or log `X-API-Key`.
20. In systems with multiple auth schemes, write tests when a request carries both `X-API-Key` and `Authorization: Bearer`; reject ambiguity or enforce policy-defined precedence.
21. Write an additional filter-only test with a spy manager measuring `0` invocations when the converter returns empty and `1` when the header is present.
22. Simulate a Redis outage, confirm the manager emits no authenticated principal, and record a sanitized metric.

## 17. Official references

- [Spring Security — ReactiveAuthenticationManager API 6.3](https://docs.spring.io/spring-security/site/docs/6.3.0-RC1/api/org/springframework/security/authentication/ReactiveAuthenticationManager.html): meaning of `Mono<Authentication>` success/empty/error.
- [Spring Security — ServerAuthenticationConverter API 6.3](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/web/server/authentication/ServerAuthenticationConverter.html): `convert(ServerWebExchange)` and empty when no attempt.
- [Spring Security — AuthenticationWebFilter API 6.3](https://docs.spring.io/spring-security/site/docs/6.3.0-M3/api/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html): converter/manager, matcher, success/failure handlers, and context repository.
- [Spring Security — Reactive WebTestClient Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html): `bindToApplicationContext(...).apply(springSecurity())`.
- [Spring Security — Reactive Authentication Test Support](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html): `mockUser()`/`@WithMockUser` and scope of mocks.
- [Spring Security — Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): CSRF conditions and application security.
- [Spring Framework — MockServerWebExchange](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/mock/web/server/MockServerWebExchange.html): mocking reactive exchanges in tests.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): mock-server vs live-server binding, HTTP assertions.
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, virtual time, timeouts, and reactive signals.
- [Project Reactor — Reactor Test API](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): `assertNext`, `expectError`, `verify(Duration)`.
- [Spring Security — Reactive HTTP Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): `authorizeExchange`, granted authorities, and deny-by-default.
- [OWASP — REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html): TLS, credential handling, authentication/authorization.
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): key storage, rotation, redaction.
- [Oracle Java 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): CSPRNG source for API keys.
- [Oracle Java 17 — MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html): SHA-256 and `MessageDigest.isEqual`.

**Key takeaway:** Test **`ServerAuthenticationConverter`** with `MockServerWebExchange` to verify **header → unauthenticated Authentication**; test **`ReactiveAuthenticationManager`** with `StepVerifier` and a fake reactive repository to verify **credential → authenticated Authentication or error**; finally, use **`WebTestClient + springSecurity()`** to send real credentials through the filter chain to verify **200/401/403** and Reactor SecurityContext. **`Mono.empty()` does not mean valid credentials**, **`mockUser()` does not test the manager/converter**, and a wrong key must emit an authentication error rather than silently allowing access.