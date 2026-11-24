# DelegatingReactiveAuthenticationManager and Coordinating Multiple Authentication Managers

> **Scope:** Spring Security **reactive** in Spring WebFlux, Spring Boot 3.x, Spring Security 6.3–6.5, and Java 17+. The topic is **`DelegatingReactiveAuthenticationManager`**, how to coordinate multiple `ReactiveAuthenticationManager` instances in order, the meaning of the three Reactor signals (`success`, `empty`, `error`), how to wire it to HTTP authentication, designing safe fallbacks, and testing. Examples use dummy credentials for learning only; production must authenticate against trusted sources, manage secrets, and enforce TLS.

## 1. Why Are Multiple Authentication Managers Needed?

An application may have multiple ways to prove identity:

- Users log in with **username/password**.
- An automated job calls an API using an **API key** or workload certificate.
- REST APIs accept **OAuth2 Bearer access tokens** (JWT or opaque).
- A system is gradually migrating from one Identity Provider to another.
- Each tenant or request path has its own authentication mechanism.

Each mechanism has a different way of reading credentials, verifying them, mapping principals, and granting authorities. Rather than one giant method full of `if/else` branches and mixed authentication logic, we can encapsulate each method inside a `ReactiveAuthenticationManager` and then **coordinate** them at the appropriate boundary.

`DelegatingReactiveAuthenticationManager` is an implementation of `ReactiveAuthenticationManager`. It takes an **ordered list of managers**, attempts to authenticate the request through each manager, and uses the appropriate result according to the contract. This is a **sequential delegation** structure based on publisher signals, not concurrent checking across mechanisms or additive authority merging.

When mechanisms are cleanly separated by **HTTP path**, **credential scheme**, or **issuer/tenant**, it is sometimes better to select the right manager upfront via `ReactiveAuthenticationManagerResolver` or separate HTTP configurations rather than trying sequentially. This lesson explains each case clearly.

### 1.1 Components in WebFlux

| Component | Responsibility |
| --- | --- |
| `ServerAuthenticationConverter` | Reads the HTTP `ServerWebExchange` and converts credentials into an **unauthenticated** `Authentication`; does not prove credentials are valid on its own |
| `AuthenticationWebFilter` | Determines requests requiring authentication, calls converter then `ReactiveAuthenticationManager`, and handles success/failure |
| `ReactiveAuthenticationManager` | Checks credentials and returns `Mono<Authentication>`, `Mono.empty()`, or `Mono.error(...)` |
| `DelegatingReactiveAuthenticationManager` | Tries multiple `ReactiveAuthenticationManager` instances in order |
| `Authentication` | Represents pre-authentication input and post-authentication result (principal, authorities, status...) |
| `ReactiveSecurityContextHolder` | Provides `SecurityContext` to the reactive request pipeline after successful authentication |
| `SecurityWebFilterChain` / `ServerHttpSecurity` | Wraps WebFilters for requests, chooses authentication mechanisms, and applies authorization |
| `ReactiveAuthenticationManagerResolver<C>` | Selects the **manager matching context C**, e.g. by request/tenant, before the authenticate step |

**Do not confuse:** `DelegatingReactiveAuthenticationManager` coordinates **authentication managers**. `SecurityWebFilterChain` coordinates **security WebFilters** for HTTP requests. `DelegatingReactiveAuthorizationManager` belongs to **authorization**, making access-control decisions; it does not verify credentials.

## 2. The Key Contract: Success, Unsupported, Failure

Functional API:

```java
@FunctionalInterface
public interface ReactiveAuthenticationManager {
    Mono<Authentication> authenticate(Authentication authentication);
}
```

This signature illustrates the concept; the actual interface resides in package `org.springframework.security.authentication`. Each manager receives a request `Authentication` (usually not yet authenticated) and returns one of three signal forms:

| Signal | Business meaning of a delegate | Effect when composing managers |
| --- | --- | --- |
| `Mono.just(authenticated)` | Valid credentials; result contains verified identity and authorities | Stops trying further; uses the first successful result |
| `Mono.empty()` | Manager **cannot decide**, e.g. does not support this `Authentication` type | Allows trying the next manager |
| `Mono.error(AuthenticationException)` | Manager is responsible for handling it, yet credentials are wrong, account is locked, or auth failed | **By default stops and emits error**; does not try next |
| `Mono.error(otherException)` | Usually a processing/infrastructure error; must be classified and handled safely | By default emits error; do not silently turn into success/empty |

Key programming rule:

> **"Unsupported" is `Mono.empty()`; "tried and failed" is `Mono.error(...)`.** Never return empty on a wrong password, expired token, or invalid JWT signature just so a manager can easily fall back to another mechanism.

In the **two managers by credential type** example:

- The password manager receives `UsernamePasswordAuthenticationToken` and **checks the password**. If wrong, it returns `BadCredentialsException`; if right, it returns an authenticated token.
- The API-key manager receives `PreAuthenticatedAuthenticationToken` built by a **controlled API-key converter**. If the key is wrong, it returns `BadCredentialsException`; if right, it returns a token with granted authorities.
- If the password manager receives `PreAuthenticatedAuthenticationToken`, it returns `Mono.empty()` because **it is not its credential type**.
- If the API-key manager receives `UsernamePasswordAuthenticationToken`, it returns `Mono.empty()` because **it does not belong to the API-key mechanism**.

### 2.1 Sequential Illustration

```text
Authentication request
        |
        v
DelegatingReactiveAuthenticationManager
        |
        +--> manager A.authenticate(request)
        |      |
        |      +-- valid Mono<Authentication> ----> RETURN RESULT
        |      +-- Mono.error(ex) ----------------> SIGNAL ERROR (default)
        |      +-- Mono.empty() ------------------+
        |                                         |
        +<----------------------------------------+
        |
        +--> manager B.authenticate(request)
               |
               +-- valid Mono<Authentication> ----> RETURN RESULT
               +-- Mono.error(ex) ----------------> SIGNAL ERROR (default)
               +-- Mono.empty() ------------------> next manager
                                                     or finish empty
```

Managers are configured in the order of `List<ReactiveAuthenticationManager>` or varargs arguments. Policy-wise, **order matters**: the first valid authentication result wins; later managers have no chance to add to or re-verify that result.

Publisher assembly can occur when `authenticate` is called, while actual I/O or reactive logic usually runs upon **subscription**. Do not call `subscribe()` or `block()` inside a manager to orchestrate; **return the `Mono`** and let the security chain/tests subscribe.

## 3. How to Create DelegatingReactiveAuthenticationManager

Two valid Spring Security 6.x ways:

```java
ReactiveAuthenticationManager combined =
    new DelegatingReactiveAuthenticationManager(passwordManager, apiKeyManager);
```

or:

```java
List<ReactiveAuthenticationManager> managers =
    List.of(passwordManager, apiKeyManager);

DelegatingReactiveAuthenticationManager combined =
    new DelegatingReactiveAuthenticationManager(managers);
```

These lines are **snippets requiring already-defined variables/managers**; import `org.springframework.security.authentication.DelegatingReactiveAuthenticationManager` and `ReactiveAuthenticationManager`.

Characteristics:

1. **The constructor does not automatically turn each delegate into a singleton Spring bean.** You must create the delegates and wire the combined manager properly into `SecurityWebFilterChain`, `AuthenticationWebFilter`, or a consumer of `ReactiveAuthenticationManager`.
2. **Does not probe "which manager supports the token" via `supports(Class)` like Servlet `AuthenticationProvider`.** The reactive contract uses `Mono.empty()` to express no decision.
3. **Does not merge authorities** across managers. If manager A succeeds, A's result is used; B does not run to add roles.
4. **Does not route HTTP headers on its own.** Basic/Bearer/API-key headers must be decoded by an appropriate converter before a manager receives `Authentication`.
5. **Does not log a user in or write sessions on its own.** It only authenticates an `Authentication` provided by the caller.

### 3.1 Semantics of setContinueOnError

In Spring Security **6.3+**, the `setContinueOnError(boolean)` API lets you choose the policy when a delegate emits an error:

```java
DelegatingReactiveAuthenticationManager combined =
    new DelegatingReactiveAuthenticationManager(primary, secondary);

// Default is false. Enable only with a very clear reason:
combined.setContinueOnError(true);
```

- When **`false` (default)**: an error from a delegate fails authentication; the next delegate is not called. If a delegate returns empty, it still proceeds.
- When **`true`**: the implementation continues trying other delegates upon errors, looking for **the first non-empty, non-error authentication result** per the 6.5 Javadoc.
- If none of the delegates authenticate successfully, do not guess a specific final exception across every version: verify the exact completion/error signal with your version and enforce a **fail-closed** policy at the call site.

**Security warning:** Using `setContinueOnError(true)` to "fall back" after `BadCredentialsException` can open a path from **rejected credentials** to a weaker provider. For example, a new mechanism locks an account yet an old provider still lets it log in. The safe approach is **having another manager process only when the earlier manager returned empty due to an unsupported token type**, or selecting providers via explicit boundaries (tenant, path, issuer, header).

Do not treat **Identity Provider downtime** the same as **invalid credentials**. Turning every error into empty or enabling continue-on-error globally breaks authentication policy and can mask operational failures. If failover is required, design an explicit failover strategy with security constraints and test every case.

## 4. Designing Delegates by Credential Type to Avoid Wrong Fallbacks

Two common ways of splitting:

| Split strategy | Example | Assessment |
| --- | --- | --- |
| By **Authentication type** | `UsernamePasswordAuthenticationToken` and `PreAuthenticatedAuthenticationToken` | Clear, easy to return empty for unsupported types; great for demonstrating delegation |
| By **issuer / tenant** | JWT of IdP A vs IdP B | Often choose `ReactiveAuthenticationManagerResolver` based on verified issuer/tenant; avoids trying random signatures repeatedly |
| By **HTTP path** | `/browser/**` vs `/api/**` | Often use multiple `SecurityWebFilterChain`s with `securityMatcher` and clear order |
| By **Authorization scheme** | `Basic` vs `Bearer` | Separate matching converter/filter, possibly separate managers; Resource Server is standard for Bearer |
| By **password providers sharing the same token type** | New directory + legacy directory | Dangerous if wrong password in provider A is treated as empty to try provider B; requires explicit identity and conflict-resolution rules |

**Coordination principle:** **A credential must be interpreted according to the exact method chosen by the client**. Never let a token already identified as a bad-signature JWT be automatically tried as a "legacy" API key or treated as username/password. That weakens security boundaries.

## 5. Java 17+ Unit Test Example: Two Managers with Two Authentication Types

The first exercise intentionally **does not start an HTTP server**: learn how to distinguish success/empty/error of `DelegatingReactiveAuthenticationManager` itself. Uses Spring Boot 3.x, JUnit 5, Reactor Test.

In a project with the Spring Boot plugin applied, add:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Create the complete file `src/test/java/com/example/delegatingauth/DelegatingManagersTest.java`:

```java
package com.example.delegatingauth;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DelegatingReactiveAuthenticationManager;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class DelegatingManagersTest {

    private static Authentication userRequest(String password) {
        return UsernamePasswordAuthenticationToken.unauthenticated(
            "alice", password
        );
    }

    private static Authentication serviceRequest(String key) {
        return new PreAuthenticatedAuthenticationToken("worker", key);
    }

    private static ReactiveAuthenticationManager passwordManager() {
        return request -> {
            if (!(request instanceof UsernamePasswordAuthenticationToken)) {
                return Mono.empty();
            }
            if (!"alice".equals(request.getName())
                    || !"correct-test-password".equals(request.getCredentials())) {
                return Mono.error(new BadCredentialsException(
                    "Invalid username/password"));
            }
            return Mono.just(UsernamePasswordAuthenticationToken.authenticated(
                "alice",
                null,
                List.of(new SimpleGrantedAuthority("ROLE_READER"))
            ));
        };
    }

    private static ReactiveAuthenticationManager apiKeyManager() {
        return request -> {
            if (!(request instanceof PreAuthenticatedAuthenticationToken)) {
                return Mono.empty();
            }
            if (!"correct-test-key".equals(request.getCredentials())) {
                return Mono.error(new BadCredentialsException(
                    "Invalid API key"));
            }
            return Mono.just(new PreAuthenticatedAuthenticationToken(
                "service-worker",
                null,
                List.of(new SimpleGrantedAuthority("SCOPE_jobs.read"))
            ));
        };
    }

    @Test
    void passwordRequestSkipsUnsupportedKeyManager() {
        AtomicInteger passwordCalls = new AtomicInteger();

        ReactiveAuthenticationManager countedPassword = request -> {
            passwordCalls.incrementAndGet();
            return passwordManager().authenticate(request);
        };
        var combined = new DelegatingReactiveAuthenticationManager(
            apiKeyManager(), countedPassword
        );

        StepVerifier.create(
                combined.authenticate(userRequest("correct-test-password"))
            )
            .assertNext(result -> {
                assertThat(result.isAuthenticated()).isTrue();
                assertThat(result.getName()).isEqualTo("alice");
                assertThat(result.getAuthorities())
                    .extracting("authority")
                    .contains("ROLE_READER");
            })
            .verifyComplete();

        assertThat(passwordCalls).hasValue(1);
    }

    @Test
    void firstSuccessStopsLaterDelegates() {
        AtomicInteger laterCalls = new AtomicInteger();
        ReactiveAuthenticationManager later = request -> {
            laterCalls.incrementAndGet();
            return Mono.error(new IllegalStateException(
                "Must not be called"));
        };

        var combined = new DelegatingReactiveAuthenticationManager(
            apiKeyManager(), later
        );

        StepVerifier.create(
                combined.authenticate(serviceRequest("correct-test-key"))
            )
            .assertNext(result -> {
                assertThat(result.isAuthenticated()).isTrue();
                assertThat(result.getName()).isEqualTo("service-worker");
                assertThat(result.getAuthorities())
                    .extracting("authority")
                    .contains("SCOPE_jobs.read");
            })
            .verifyComplete();

        assertThat(laterCalls).hasValue(0);
    }

    @Test
    void wrongPasswordIsErrorAndDoesNotTryNextManager() {
        AtomicInteger fallbackCalls = new AtomicInteger();
        ReactiveAuthenticationManager riskyFallback = request -> {
            fallbackCalls.incrementAndGet();
            return Mono.just(UsernamePasswordAuthenticationToken.authenticated(
                "alice", null,
                List.of(new SimpleGrantedAuthority("ROLE_READER"))));
        };

        var combined = new DelegatingReactiveAuthenticationManager(
            passwordManager(), riskyFallback
        );

        StepVerifier.create(
                combined.authenticate(userRequest("WRONG"))
            )
            .expectError(BadCredentialsException.class)
            .verify();

        assertThat(fallbackCalls).hasValue(0);
    }

    @Test
    void wrongApiKeyIsAlsoError() {
        var combined = new DelegatingReactiveAuthenticationManager(
            passwordManager(), apiKeyManager()
        );

        StepVerifier.create(
                combined.authenticate(serviceRequest("WRONG"))
            )
            .expectError(BadCredentialsException.class)
            .verify();
    }

    @Test
    void unsupportedByAllManagersIsEmpty() {
        var combined = new DelegatingReactiveAuthenticationManager(
            passwordManager(), apiKeyManager()
        );

        Authentication unsupported = new TestingAuthenticationToken(
            "anything", "anything"
        );

        StepVerifier.create(combined.authenticate(unsupported))
            .verifyComplete();
    }

    @Test
    void continueOnErrorAllowsNextManagerToSucceed() {
        AtomicInteger secondCalls = new AtomicInteger();

        ReactiveAuthenticationManager rejects = request ->
            Mono.error(new BadCredentialsException("Rejected by first"));

        ReactiveAuthenticationManager second = request -> {
            secondCalls.incrementAndGet();
            return Mono.just(UsernamePasswordAuthenticationToken.authenticated(
                "alice", null,
                List.of(new SimpleGrantedAuthority("ROLE_READER"))));
        };

        var combined = new DelegatingReactiveAuthenticationManager(
            rejects, second
        );
        combined.setContinueOnError(true);

        StepVerifier.create(combined.authenticate(userRequest("WRONG")))
            .assertNext(result ->
                assertThat(result.getName()).isEqualTo("alice"))
            .verifyComplete();

        assertThat(secondCalls).hasValue(1);
    }
}
```

**Explanation of test scope:** `passwordManager()` and `apiKeyManager()` in this file are **test delegates** using fixed credential strings to demonstrate the contract, not production providers. `TestingAuthenticationToken` is solely a testing token; `PreAuthenticatedAuthenticationToken` here is only **selected by type** and checked for the key by test code. In real systems, you must verify credential sources, account policies, and granted authorities.

Run:

```bash
./gradlew test --tests '*DelegatingManagersTest'
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests '*DelegatingManagersTest'
```

**Expected `StepVerifier` results table**, not stdout observed on this machine:

| Test | Expected signal | Subsequent delegate |
| --- | --- | --- |
| `passwordRequestSkipsUnsupportedKeyManager` | Authenticated Alice, `ROLE_READER` | Password manager invoked exactly once |
| `firstSuccessStopsLaterDelegates` | Authenticated service-worker, `SCOPE_jobs.read` | Later manager does **not** run |
| `wrongPasswordIsErrorAndDoesNotTryNextManager` | `BadCredentialsException` | Fallback does **not** run because `continueOnError=false` |
| `wrongApiKeyIsAlsoError` | `BadCredentialsException` | No authenticated result |
| `unsupportedByAllManagersIsEmpty` | Completes **without emitting Authentication** | All managers declined to handle the type |
| `continueOnErrorAllowsNextManagerToSucceed` | Successful result from second manager | Proves why enabling error fallback can be dangerous |

**Never copy the last test's policy into production.** It intentionally lets credentials rejected by manager A still be authenticated by manager B to illustrate the risk of widening the trust boundary.

### 5.1 Signal Table Including Ordering

Consider these independent outcome sequences:

```text
A = empty, B = success    -> success from B
A = success, B = anything -> success from A, B does not run
A = error, B = success    -> error from A (default)
A = empty, B = empty      -> empty
A = empty, B = error      -> error from B
A = error, B = success    -> may reach B if continueOnError(true)
```

Remember that **"empty" does not mean wrong password**. It means the manager **lacks basis/does not claim responsibility** for authenticating that request per the contract. Do not turn every authentication exception into empty with `onErrorResume(e -> Mono.empty())` just to run through other providers.

## 6. Wiring into WebFlux HTTP: Converter → Manager → SecurityContext

`DelegatingReactiveAuthenticationManager` itself **cannot read** `Authorization` or `X-API-Key` from an HTTP request. In WebFlux, that job belongs to filters and converters:

```text
Request to WebFlux
  |
  v
AuthenticationWebFilter / httpBasic() filter
  |
  +--> ServerAuthenticationConverter
  |       Basic header -> UsernamePasswordAuthenticationToken (unauthenticated)
  |       X-API-Key    -> PreAuthenticatedAuthenticationToken (unauthenticated)
  |
  v
DelegatingReactiveAuthenticationManager
  |
  +--> passwordManager for UsernamePasswordAuthenticationToken
  +--> apiKeyManager for PreAuthenticatedAuthenticationToken
  |
  +--> success: SecurityContext placed into reactive pipeline
  +--> error: handled by authentication failure handler
  +--> empty: no authenticated result, policy must deny protected requests
  |
  v
authorizeExchange / method authorization -> Controller or RouterFunction
```

In practice, there may be **two `AuthenticationWebFilter`s** or one DSL-created filter plus one custom filter sharing a combined manager. They typically have separate converters so the boundary between Basic and API key does not blur.

`AuthenticationWebFilter` has two primary entry points:

```java
new AuthenticationWebFilter(reactiveAuthenticationManager);
new AuthenticationWebFilter(authenticationManagerResolver);
```

And has:

```java
filter.setServerAuthenticationConverter(converter);
filter.setRequiresAuthenticationMatcher(matcher);
filter.setSecurityContextRepository(repository);
```

This is an illustrative snippet, not a standalone file. In Spring Security WebFlux, when a converter returns `Mono.empty()`, the filter understands **the request contains no matching credentials to attempt**, so it does not invoke the authentication manager. **This is a different empty layer** from `Mono.empty()` returned by a delegate manager.

### 6.1 Example Integrating Two Credential Types in One Application Context

The example below uses:

- `GET /user/me` authenticated via **HTTP Basic**, handled by the password manager.
- `GET /service/me` authenticated via **X-API-Key** for automated jobs, handled by the API-key manager.
- One `DelegatingReactiveAuthenticationManager` taking two mutually exclusive managers by type.
- One `SecurityWebFilterChain` registering HTTP infrastructure, where the Basic filter uses the combined manager and a custom `AuthenticationWebFilter` uses that same combined manager.
- Authorization distinguishes roles/scopes: user needs `ROLE_READER`; service needs `SCOPE_service.read`.

This is a **learning pattern**. For production service-to-service communication, prefer OAuth2 client credentials or workload identity/mTLS; API keys are suitable only with full lifecycle/rate-limit/monitoring design.

In `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Use only `spring-boot-starter-webflux` as the web server in this lesson. If you also add `spring-boot-starter-web`, Spring Boot 3.x usually selects Servlet/MVC by default and this `SecurityWebFilterChain` no longer describes the running HTTP stack.

Source layout:

```text
src/main/java/com/example/delegatingauth/
  DelegatingAuthApplication.java
  DelegatingSecurityConfig.java
  IdentityController.java
src/test/java/com/example/delegatingauth/
  DelegatingManagersTest.java
  DelegatingHttpTest.java
src/main/resources/
  application.yml
```

### 6.2 DelegatingAuthApplication.java

`src/main/java/com/example/delegatingauth/DelegatingAuthApplication.java`:

```java
package com.example.delegatingauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DelegatingAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(DelegatingAuthApplication.class, args);
    }
}
```

### 6.3 DelegatingSecurityConfig.java: Combined Manager and HTTP Filters

`src/main/java/com/example/delegatingauth/DelegatingSecurityConfig.java`:

```java
package com.example.delegatingauth;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DelegatingReactiveAuthenticationManager;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.AuthenticationWebFilter;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class DelegatingSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        var user = User.withUsername("alice")
            .password(encoder.encode("demo-user-password"))
            .roles("READER")
            .build();
        return new MapReactiveUserDetailsService(user);
    }

    @Bean
    ReactiveAuthenticationManager combinedManager(
            MapReactiveUserDetailsService users,
            PasswordEncoder encoder,
            @Value("${demo.api-key}") String expectedApiKey) {

        if (expectedApiKey == null || expectedApiKey.isBlank()) {
            throw new IllegalArgumentException("API key must be configured");
        }

        var passwordDelegate =
            new UserDetailsRepositoryReactiveAuthenticationManager(users);
        passwordDelegate.setPasswordEncoder(encoder);

        // UserDetails manager is only called for username/password.
        ReactiveAuthenticationManager passwordOnly = request -> {
            if (!(request instanceof UsernamePasswordAuthenticationToken)) {
                return Mono.empty();
            }
            return passwordDelegate.authenticate(request);
        };

        // Demo: pre-auth token is unauthenticated yet; STILL MUST verify API key.
        byte[] expectedDigest = sha256(expectedApiKey);
        ReactiveAuthenticationManager apiKeyOnly = request -> {
            if (!(request instanceof PreAuthenticatedAuthenticationToken)) {
                return Mono.empty();
            }
            Object credentials = request.getCredentials();
            if (!(credentials instanceof String supplied)
                    || !MessageDigest.isEqual(
                            expectedDigest, sha256(supplied))) {
                return Mono.error(new BadCredentialsException(
                    "Invalid API key"));
            }

            return Mono.just(new PreAuthenticatedAuthenticationToken(
                "trusted-service",
                null,
                List.of(new SimpleGrantedAuthority("SCOPE_service.read"))
            ));
        };

        // Order does not change responsibility: unsupported type -> empty.
        return new DelegatingReactiveAuthenticationManager(
            passwordOnly, apiKeyOnly
        );
    }

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager combinedManager) {

        // Dedicated filter tries X-API-Key only on service paths.
        var apiKeyFilter = new AuthenticationWebFilter(combinedManager);
        apiKeyFilter.setRequiresAuthenticationMatcher(
            new PathPatternParserServerWebExchangeMatcher("/service/**")
        );
        apiKeyFilter.setServerAuthenticationConverter(exchange -> {
            String rawKey = exchange.getRequest().getHeaders()
                .getFirst("X-API-Key");
            if (rawKey == null || rawKey.isBlank()) {
                return Mono.empty();
            }
            return Mono.just(new PreAuthenticatedAuthenticationToken(
                "api-key-request", rawKey
            ));
        });
        apiKeyFilter.setSecurityContextRepository(
            NoOpServerSecurityContextRepository.getInstance()
        );

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/user/**").hasRole("READER")
                .pathMatchers("/service/**").hasAuthority(
                    "SCOPE_service.read")
                .anyExchange().denyAll()
            )
            .httpBasic(basic -> basic.authenticationManager(combinedManager))
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .addFilterAt(
                apiKeyFilter,
                SecurityWebFiltersOrder.AUTHENTICATION
            )
            .build();
    }

    private static byte[] sha256(String text) {
        try {
            return MessageDigest.getInstance("SHA-256")
                .digest(text.getBytes(StandardCharsets.UTF_8));
        }
        catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }
}
```

**Code explanation:**

1. `UserDetailsRepositoryReactiveAuthenticationManager` checks passwords using `ReactiveUserDetailsService` and `PasswordEncoder`. We **wrap** it with `passwordOnly` so any request that is not a `UsernamePasswordAuthenticationToken` receives `Mono.empty()` before calling the delegate. Do not assume every framework manager handles wrong token types identically.
2. `apiKeyOnly` only accepts `PreAuthenticatedAuthenticationToken` produced by the API-key converter. **PreAuthenticated** is the token class name, **not a guarantee that the key is already verified**. It still matches the expected digest and only returns an authenticated token **after** verification succeeds.
3. `MessageDigest.isEqual` compares two equal-length SHA-256 digests; in the demo, the configured secret lives in the environment rather than hardcoded in Java. Production needs hashed/HMAC key storage or a secret-management system, rotation, expiry/revocation, and access limits; plain SHA-256 alone is not a complete API-key management solution.
4. `httpBasic(...authenticationManager(combinedManager))` wires the combined manager into the Basic flow managed by Spring Security. The Basic converter creates a username/password token. It **does not read `X-API-Key`**.
5. The custom `AuthenticationWebFilter` uses a converter reading `X-API-Key` only on `/service/**`. Without the header, the converter returns empty so the manager is not tried. If the key is present yet wrong, the API-key manager emits an error; never return empty to let a user slip through another mechanism.
6. `NoOpServerSecurityContextRepository` does not save authentication into a session for the API-key filter, yet a successful request still has a reactive SecurityContext during current processing; the next request must present its credential again.
7. `authorizeExchange` is **post-authentication authorization**. `alice` has `ROLE_READER` so she can access `/user/**`; `trusted-service` has `SCOPE_service.read` so it can access `/service/**`.
8. Two authentication filters can both inspect a request if multiple credential types appear. The example is designed for **one expected mechanism per request**. In real products, establish an explicit **credential precedence** policy, rejecting or controllably handling requests carrying both Basic and API key; split chains/filters by path when strict separation is required.
9. CSRF is not disabled in the sample; the example is GET-only so no CSRF token is needed. If adding state-changing endpoints, protect browser cookies with CSRF and carefully examine credential mechanisms before configuring a stateless API.

**Safety note:** The example keeps a demo password in code for instruction. Never apply such hard-coded users/keys outside learning environments. API keys remain bearer secrets: require HTTPS, never log them, never put them in URLs/queries, and never send them to untrusted origins.

### 6.4 IdentityController.java: Two Endpoints Reading the Principal

`src/main/java/com/example/delegatingauth/IdentityController.java`:

```java
package com.example.delegatingauth;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class IdentityController {

    @GetMapping("/user/me")
    public Mono<String> user() {
        return principalName();
    }

    @GetMapping("/service/me")
    public Mono<String> service() {
        return principalName();
    }

    private Mono<String> principalName() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(auth -> auth.getName());
    }
}
```

This controller **does not authenticate passwords/API keys**. It simply reads the `Authentication` that WebFilters placed into the Reactor Context upon successful authentication. Therefore you must keep the `SecurityWebFilterChain` intact and avoid bypassing filters in tests.

### 6.5 application.yml: Passing the Key from Environment

`src/main/resources/application.yml`:

```yaml
demo:
  api-key: ${DEMO_API_KEY}
```

Before running, supply `DEMO_API_KEY` via a secure configuration mechanism. For example, in a dedicated development terminal, set the environment variable for **that process** using your tool. Never commit real values to git, and never put secrets into docs or HTTP request logs.

Run the application with Gradle wrapper:

```bash
./gradlew bootRun
```

In Windows PowerShell: `.\gradlew.bat bootRun`. If the environment variable is missing or blank, startup fails by design; that is fail-fast, not a reason to hardcode production credentials.

## 7. HTTP Tests Verifying Two Mechanisms Through the Same Manager

In the example above, add an integration test launching the full WebFlux application with a **test-only** key and verifying the real HTTP filter chain.

`src/test/java/com/example/delegatingauth/DelegatingHttpTest.java`:

```java
package com.example.delegatingauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "demo.api-key=test-only-service-key"
)
class DelegatingHttpTest {

    @Autowired
    WebTestClient client;

    @Test
    void basicPasswordAuthenticatesUserEndpoint() {
        client.get()
            .uri("/user/me")
            .headers(h -> h.setBasicAuth(
                "alice", "demo-user-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("alice");
    }

    @Test
    void apiKeyAuthenticatesServiceEndpoint() {
        client.get()
            .uri("/service/me")
            .header("X-API-Key", "test-only-service-key")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("trusted-service");
    }

    @Test
    void missingCredentialCannotAccessProtectedEndpoints() {
        client.get()
            .uri("/user/me")
            .exchange()
            .expectStatus().isUnauthorized();

        client.get()
            .uri("/service/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void incorrectBasicPasswordIsRejected() {
        client.get()
            .uri("/user/me")
            .headers(h -> h.setBasicAuth("alice", "WRONG"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void incorrectApiKeyIsRejected() {
        client.get()
            .uri("/service/me")
            .header("X-API-Key", "WRONG")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void basicUserCannotUseServiceOnlyAuthority() {
        client.get()
            .uri("/service/me")
            .headers(h -> h.setBasicAuth(
                "alice", "demo-user-password"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

Run:

```bash
./gradlew test --tests '*DelegatingHttpTest'
```

The statuses are **expectations of the sample configuration**, not stdout observed from a local build here. If a test bypasses the SecurityWebFilterChain (e.g., a slice test binding directly to the controller), results may not reflect real security. For requests carrying both credential types simultaneously, the sample needs an explicit policy before being considered production-ready.

| Request | Authentication manager actually handling it | Required authority | Expected |
| --- | --- | --- | --- |
| `GET /user/me` + valid Basic | Password | `ROLE_READER` | 200, `alice` |
| `GET /service/me` + valid API key | API key | `SCOPE_service.read` | 200, `trusted-service` |
| Both routes above without credentials | No valid authentication result | Blocked | 401 |
| Wrong password / wrong API key | Corresponding manager emits `BadCredentialsException` | Not granted access | 401 with appropriate handler |
| Valid Basic calling `/service/me` | Password authentication succeeded | Missing `SCOPE_service.read` | 403 |

**Inference:** `DelegatingReactiveAuthenticationManager` only decides **which identity was proven by which credential**. `hasRole` / `hasAuthority` decides **whether that identity may access the endpoint**. 401 and 403 come from HTTP policies/filters; `authenticate` does not return status codes directly.

## 8. When to Use a Resolver Instead of Trying All Delegates?

`ReactiveAuthenticationManagerResolver<ServerWebExchange>` can return the manager appropriate for the **request context**, whereas `DelegatingReactiveAuthenticationManager` tries multiple managers on **the same Authentication object**.

For example, with two tenants, each having its own JWT issuer:

- Parse the request/claim needed to identify the issuer.
- Select only the trusted manager/decoder registered for that issuer.
- The selected manager must still verify signature, `iss`, `aud`, expiration, and token policies.
- Never try tenant A's JWT against tenant B's manager just because A reported an invalid signature.

Spring Security has standard integrations for resource servers and multi-tenancy such as `JwtReactiveAuthenticationManager`, `ReactiveJwtDecoder`, and `JwtIssuerReactiveAuthenticationManagerResolver` (depending on version/configuration). Use them for JWT and issuer problems; never write a custom token parser or trust unverified claims for authorization.

Below is **routing pseudocode** for illustration, not standalone code:

```text
Request -> determine trusted tenant/issuer candidate
        -> ReactiveAuthenticationManagerResolver.resolve(request)
        -> selected JwtReactiveAuthenticationManager
        -> validate signature/iss/aud/exp/scope
        -> authenticated principal or reject
```

If you only need **Basic for browsers** and **Bearer for APIs**, configuring separate WebFlux HTTP Basic / OAuth2 Resource Server mechanisms in `ServerHttpSecurity`, or multiple `SecurityWebFilterChain`s with path-based `securityMatcher`s, is cleaner than chaining two validators into a blind fallback.

### 8.1 Differences Between Resolver and DelegatingReactiveAuthenticationManager

| Criterion | DelegatingReactiveAuthenticationManager | ReactiveAuthenticationManagerResolver |
| --- | --- | --- |
| Primary input | An `Authentication` request | Context such as `ServerWebExchange` |
| Decision | Tries a list of managers sequentially based on signals | Selects a manager by context/tenant/path |
| Return type | `Mono<Authentication>` | `Mono<ReactiveAuthenticationManager>` |
| When it stops | First success; errors stop by default | Depends on resolver; the selected manager authenticates |
| Best fit | Multiple delegates that reject unsupported types via empty | Tenant, issuer, route, or policy determines the manager |
| Design risk | Bad fallback after BadCredentials, manager ordering | Trusting unverified routing data or mis-mapping tenants |

## 9. Common Confusions with Servlet Authentication

Reactive Spring Security applications use:

- `ReactiveAuthenticationManager`, `DelegatingReactiveAuthenticationManager`.
- `AuthenticationWebFilter` and `ServerHttpSecurity`.
- `SecurityWebFilterChain` and `ReactiveSecurityContextHolder`.

Servlet/MVC applications have concepts like `AuthenticationManager`, `ProviderManager`, `AuthenticationProvider`, `HttpSecurity`, and `SecurityFilterChain`. Goals may look similar, yet APIs and request pipelines are **different**. Never plug `ProviderManager` into `AuthenticationWebFilter` or assume `DelegatingReactiveAuthenticationManager` is an adapter for Servlet providers.

If an app includes both `spring-boot-starter-web` and `spring-boot-starter-webflux`, Spring Boot 3.x usually defaults to MVC. Verify the application context is reactive before applying the WebFlux configurations in this lesson. Having `Mono` in a controller does not prove requests pass through reactive security.

## 10. Real-World Mistakes and Fixes

### 10.1 Returning empty after a failed password check

**Wrong:**

```java
ReactiveAuthenticationManager wrong = request ->
    checkPassword(request)
        .onErrorResume(BadCredentialsException.class, error -> Mono.empty());
```

This is a **snippet** depending on a `checkPassword` method. It turns "checked and wrong" into "don't know how to handle", allowing a delegating manager to run another provider. If the other provider accepts credentials under weaker rules, you have created a bypass.

**Right:** For matching-type yet wrong credentials, preserve `Mono.error(new BadCredentialsException(...))`. Only return empty before verifying credentials when **the token type is outside this manager's responsibility**.

### 10.2 Accepting any Authentication and casting blindly

**Wrong:**

```java
ReactiveAuthenticationManager manager = authentication -> {
    UsernamePasswordAuthenticationToken token =
        (UsernamePasswordAuthenticationToken) authentication;
    return verifyPassword(token);
};
```

This snippet can throw `ClassCastException` when the manager list receives an API-key token. Check `instanceof`, return empty for unsupported types, and cast safely or use Java 17 pattern matching.

### 10.3 Using success to prove two authentication steps completed

A `DelegatingReactiveAuthenticationManager(A, B)` **does not mean "must pass both A and B"**. It uses **the first matching result**. If policy requires MFA (password + OTP) or both mTLS and a token, you must build an **authentication flow verifying all required factors** via the corresponding Spring Security mechanism; never treat delegation as logical AND.

### 10.4 Returning an authenticated token before verification

`new PreAuthenticatedAuthenticationToken(principal, credentials, authorities)` is the **constructor that creates an authenticated token**. Call it only after verifying the credential source genuinely succeeded, or in tests. The class name `PreAuthenticated` does not create trust automatically.

### 10.5 Manual subscribe, block, or swallowing errors

Never call `manager.authenticate(request).block()` on the WebFlux event loop; never call `subscribe` and store the Authentication in a shared variable. Keep the chain:

```java
return manager.authenticate(request)
    .switchIfEmpty(Mono.error(
        new BadCredentialsException("No manager accepted credentials")))
    .flatMap(this::runForAuthenticatedPrincipal);
```

The snippet above assumes the class has `runForAuthenticatedPrincipal(Authentication)` returning a compatible publisher. Turning `empty` into an error must be done by a **policy-aware caller**; never map every system disconnect or server outage to `BadCredentialsException`. Never log raw credentials, `Authentication.getCredentials()`, Bearer tokens, or API keys.

### 10.6 Mixing up authentication and authorization

A manager returns an `Authentication` with authorities. The API still needs `authorizeExchange`/method authorization, plus tenant/resource ownership checks. Never treat "authenticated" as "allowed to read every resource".

### 10.7 Configuring multiple chains without knowing which one runs

When there are multiple `SecurityWebFilterChain`s, `securityMatcher` and `@Order` determine which chain handles a request. A request typically selects **only the first matching chain**, not all chains sequentially trying every manager. Do not confuse **selecting a security chain** with **delegating managers inside a filter**.

### 10.8 Feeding credentials from untrusted sources into a strong provider

Never rely on an `X-Tenant` header or unverified-signature JWT claim to grant permissions or pick trusted keys arbitrarily. If resolving by tenant/issuer, restrict to an allowlist and verify inside the chosen manager. If a request carries both Basic and X-API-Key simultaneously, define an explicit reject/precedence policy instead of letting filter order accidentally pick the principal.

### 10.9 Valid credentials yet missing permission

This is an **authorization error (403)**, not a reason to invoke another authentication manager. Access grants must be based on verified authentication results and endpoint policies.

### 10.10 Depending on blocking I/O inside a reactive delegate

Managers must return publishers. Calling a blocking database/client directly on the WebFlux event loop can stall the app. Use reactive repositories/clients; if forced to integrate blocking legacy code, isolate it on an appropriate scheduler and evaluate load, timeouts, and circuit breakers. Do not assume `Mono.just(blockingCall())` is non-blocking: `blockingCall()` already ran synchronously before the Mono was created.

## 11. Quick Diagnostic Table

| Symptom | Common cause | What to check |
| --- | --- | --- |
| Second delegate is never called | First delegate emits success or error | Test `Mono.empty` vs `Mono.error` signals and ordering |
| Wrong password still logs in | continue-on-error enabled or BadCredentials converted to empty | Emit error for recognized credentials; block weak fallback |
| Valid API key returns 401 | Converter builds wrong token, wrong matcher, manager not registered, wrong key | HTTP filter, `ServerAuthenticationConverter`, request type, manager |
| Valid Basic gets 403 on service route | Authentication succeeded yet lacks required authority | `ROLE_*` vs `SCOPE_*` and authorization policy |
| Broken JWT still accepted by another mechanism | Trying multiple managers after validation error | Issuer/scheme boundaries; remove token-error fallback |
| No HTTP request yet manager is called | Test/service caller directly invokes `authenticate` | Distinguish manager unit calls from WebFilter/HTTP |
| `Mono.empty()` leads to unexpected behavior | Manager made no decision, caller's empty handling unclear | Test fail-closed policy at HTTP/service boundaries |
| Poor performance when trying many providers | Sequential delegates each doing I/O | Route credentials early, avoid hitting multiple IdPs needlessly |
| Unit tests pass yet WebFlux API still returns 401 | Converter/filter/chain/matcher inactive | `@SpringBootTest` integration test with `WebTestClient` |
| Authenticated Authentication object yet anonymous | Wrong token/authorities built after verification | Check principal mapping and credential lifecycle |

## 12. Self-Check Exercises

**Exercise 1 — signal model.** Manager A returns `Mono.empty()` for `PreAuthenticatedAuthenticationToken`, while manager B verifies the key and returns an authenticated token. Result? **Uses B**. A neither authenticated nor rejected; it simply does not support the request type.

**Exercise 2 — credential error.** Manager A checks the password and emits `BadCredentialsException`; B could grant `ROLE_READER`. By default, is B called? **No**. The error from A stops delegation. Never enable continue-on-error to "rescue" a wrong password.

**Exercise 3 — all empty.** If both A and B return empty, is the request considered authenticated? **No**. There is no successful `Authentication`. The caller/web layer must enforce a fail-closed policy.

**Exercise 4 — ordering.** Can swapping the order of two managers change the result? **Yes**, especially if both can handle the same token type. Separate responsibilities explicitly so ordering does not become an accidental authorization mechanism.

**Exercise 5 — JWT and API key.** A JWT is recognized yet has a bad signature; can the JWT value be tried as an API key to log in? **No.** That is a credential rejected by a specific mechanism, not an unsupported request for another provider.

**Exercise 6 — MFA.** Does calling `new DelegatingReactiveAuthenticationManager(password, otp)` force the user through both password and OTP? **No**. A delegating manager usually takes the first successful result rather than combining two authentication factors.

**Exercise 7 — WebFilter.** Does adding a `@Bean DelegatingReactiveAuthenticationManager` without configuring HTTP converters/filters automatically read `X-API-Key`? **No**. You need a filter/converter reading the header and invoking the manager, plus authorization in `SecurityWebFilterChain`.

**Exercise 8 — 401 vs 403.** Correct password, yet user lacks `SCOPE_service.read` when calling `/service/me`? **403** per authorization policy. Never forward the request to another manager to "ask for more scopes".

## 13. Project Adoption Checklist

- [ ] Identified credential types and the **`Authentication` object representing each type**.
- [ ] Each delegate returns **`Mono.empty()` only when it cannot decide/does not support the request**.
- [ ] Wrong credentials, locked account, bad token signature, expired token → **error**, never converted to empty.
- [ ] Delegate order is intentional; first success wins; never assume "passed all managers".
- [ ] Keep `setContinueOnError(false)` by default unless an approved and tightly tested failover policy exists.
- [ ] Headers/cookies/tokens are converted into **unauthenticated** `Authentication`s via valid converters.
- [ ] Filters or `ServerHttpSecurity` actually use the combined manager; do not just declare a bean and leave it unused.
- [ ] `hasRole`/`hasAuthority`, tenant, and ownership are checked after authentication.
- [ ] When route/tenant/issuer identifies the manager clearly, consider a resolver or separate chain instead of trying everything.
- [ ] Do not use Servlet `ProviderManager` inside a WebFlux reactive chain.
- [ ] Have `StepVerifier` unit tests for success/empty/error/order and `WebTestClient` HTTP tests for 401/403/200.
- [ ] Secrets are protected, TLS enforced, rotation/revocation in place, credentials never logged, and I/O never blocks the event loop.

**Takeaway:** `DelegatingReactiveAuthenticationManager` chains multiple `ReactiveAuthenticationManager`s into a **sequential attempt process**. **`Mono.empty()` says "not my responsibility"; `Mono.error()` says "authentication failed"; `Mono.just(authenticated)` says "authenticated successfully".** This distinction governs both functionality and system security.

### Official References

- [Spring Security 6.5 — DelegatingReactiveAuthenticationManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/DelegatingReactiveAuthenticationManager.html)
- [Spring Security 6.5 — ReactiveAuthenticationManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html)
- [Spring Security 6.5 — AuthenticationWebFilter Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html)
- [Spring Security 6.5 — ServerHttpSecurity Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
