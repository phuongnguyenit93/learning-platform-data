# ReactiveAuthenticationManager and the `Mono<Authentication>` Contract

## 1. Lesson Objectives

In Spring Security running on **Spring WebFlux**, authentication handling must cooperate with the Reactor chain instead of assuming every operation is always synchronous. `ReactiveAuthenticationManager` is the interface responsible for **attempting to authenticate** an `Authentication` object and returning the result according to the `Mono<Authentication>` contract.

Understanding this contract helps you see why a login request can **succeed**, **be rejected**, or **not be handled by the current manager**; at the same time, it helps avoid dangerous mistakes such as treating a wrong password as `Mono.empty()`, marking a token authenticated yourself, or calling `block()` on the event loop.

After this lesson, you should be able to:
1. Read the `authenticate(Authentication)` signature accurately and distinguish the three `Mono` signal types.
2. Know how the input `Authentication` differs from the authenticated output object.
3. Understand the relationship between `ReactiveAuthenticationManager`, `ReactiveUserDetailsService`, `AuthenticationWebFilter`, `SecurityWebFilterChain`, and Reactor `Context`.
4. Configure a built-in manager to authenticate username/password in Spring Security reactive.
5. Test success/error/empty yourself with `StepVerifier` and verify HTTP Basic with `WebTestClient`.
6. Know when a custom manager is needed, how to combine multiple managers, and principles for avoiding blocking or leaking authentication data.

> Scope: the `ReactiveAuthenticationManager` contract in Spring Security **reactive**, with Java 17+, Spring WebFlux, and HTTP Basic examples. Password encoding, JWT/OAuth2, and identity management are mentioned as needed to understand the interface; this lesson does not build a production authentication system.

## 2. Core Contract

The interface belongs to the `org.springframework.security.authentication` package:

```java
@FunctionalInterface
public interface ReactiveAuthenticationManager {
    Mono<Authentication> authenticate(Authentication authentication);
}
```

This is a **conceptual signature abridged from the API**, not a file to recreate in your project. Related types:
- `Authentication` (`org.springframework.security.core.Authentication`) describes identity, credentials, authorities, authentication status, and some additional details.
- `Mono<Authentication>` (`reactor.core.publisher.Mono`) is a publisher that emits at most **one** `Authentication` object, or completes empty, or emits an error.
- `ReactiveAuthenticationManager` is a **functional interface**, so it can be implemented via a class or lambda, but any implementation must adhere to the meaning of the three signals.

### Three Outcomes to Distinguish

| Signal from `authenticate(...)` | Meaning in the contract | Valid example |
| --- | --- | --- |
| `onNext(authenticated)` then `onComplete()` | Authentication **succeeded** | Valid user/password; result contains verified principal and authorities |
| `onComplete()` **without `onNext`** | Manager **cannot decide / does not support** this request | An API-key-only manager receives a username/password token |
| `onError(authenticationException)` | Manager processed the request but **authentication failed** | Wrong password, locked account, invalid token |

The key to reading the contract: **`Mono.empty()` is not equivalent to a wrong password.** Wrong credentials are an authentication failure and must be expressed with an appropriate error; empty is reserved for a manager that cannot determine a result. Do not use `null` as an emitted item of a `Mono` because Reactor does not allow `onNext(null)`.

Three branches in pseudocode:

```java
ReactiveAuthenticationManager manager = request -> {
    if (!supportsThisTokenType(request)) {
        return Mono.empty(); // Cannot authenticate this token type
    }
    if (!credentialsAreValid(request)) {
        return Mono.error(
                new BadCredentialsException("Invalid credentials"));
    }
    Authentication verified = createAuthenticatedResult(request);
    return Mono.just(verified);
};
```

This is **structural illustrative code** and does not compile standalone because the three methods `supportsThisTokenType`, `credentialsAreValid`, and `createAuthenticatedResult` only represent business logic. Below there is a runnable project with a built-in manager and real tests for the three signals.

### `Mono` Is Lazy

`authenticate(...)` returns a publisher; data access and credential checking in a true reactive implementation typically happen when the publisher is subscribed to. Do not rely on the method call site alone to assume every step has executed: synchronous operations outside `Mono.defer(...)` or `Mono.fromCallable(...)` can still run eagerly.

Crucially, **do not subscribe manually or block** inside a WebFlux HTTP handler. The framework and security chain subscribe at the right place and coordinate the signals.

## 3. Input and Output `Authentication`

Although both share the `Authentication` interface, before and after authentication have different meanings.

### Unauthenticated Input

When HTTP Basic receives a username/password, the HTTP converter usually creates an `Authentication` representing an **authentication request**. For example:

```java
Authentication request =
        UsernamePasswordAuthenticationToken.unauthenticated(
                "reader", "reader-pass");
```

In Spring Security 6.x, the `unauthenticated(...)` factory creates a token with no granted authorities and `isAuthenticated()` set to `false`. At this point the username is client-declared data; the password has **not yet been verified**. Never trust authorities sent by the client.

### Authenticated Result

After the manager verifies credentials, a successful result usually contains:
- Verified principal (`UserDetails` or another principal).
- `GrantedAuthority`/roles fetched from a trusted source.
- `isAuthenticated() == true`.
- Credentials may have been erased/no longer retained as a raw string.

Illustrative example of the factory on an already-verified identity source:

```java
Authentication verified =
        UsernamePasswordAuthenticationToken.authenticated(
                userDetails,
                null,
                userDetails.getAuthorities());
```

This is an **excerpt**; the variable `userDetails` must be a `UserDetails` object retrieved and verified properly. Do not call the `authenticated(...)` factory just because a username was read from a request; doing so would bypass credential verification.

| Property | Authentication request | Authentication result |
| --- | --- | --- |
| `getPrincipal()` | Usually client-sent username | Verified identity, possibly `UserDetails` |
| `getCredentials()` | Client-supplied password/token | Should have limited retention, may be erased |
| `getAuthorities()` | Untrusted if coming from client | Authorities from a trusted source |
| `isAuthenticated()` | `false` in initial login token | `true` once authenticated |
| Purpose | Request verification from manager | Provide identity for authorization |

Avoid concluding that every authentication mechanism is username/password: bearer tokens, certificates, OAuth2, and other mechanisms have their own `Authentication`/manager types.

## 4. Where Does the Manager Sit in Spring Security Reactive?

Conceptual diagram for **HTTP Basic in WebFlux**:

```text
HTTP request
   |
   v
SecurityWebFilterChain (selects security chain)
   |
   v
AuthenticationWebFilter (for the appropriate authentication mechanism)
   |
   +--> ServerAuthenticationConverter
   |         |
   |         +--> Mono<Authentication> request
   |
   +--> ReactiveAuthenticationManager.authenticate(request)
               |
               +--> onNext(verified Authentication): success
               |           |
               |           v
               |    SecurityContext / Reactor Context
               |           |
               |           v
               |    Authorization -> Controller
               |
               +--> onError(AuthenticationException): failure
               |           |
               |           v
               |    Authentication failure handler (HTTP Basic typically 401)
               |
               +--> empty: manager has no decision
                           (subsequent behavior depends on filter/manager composition)
```

The diagram explains component relationships and does not promise the exact ordering of every internal WebFilter. `AuthenticationWebFilter` is responsible for deciding when to attempt authentication, converting the request into an `Authentication` object, invoking the manager, and translating the result into success/failure handling. `SecurityWebFilterChain` composes the WebFilters; `ServerHttpSecurity` is the DSL to configure the chain.

**`ReactiveAuthenticationManager` is not an authorization manager.** It answers "can this user/token be authenticated?". `authorizeExchange(...)`/`hasRole(...)` answers "is this authenticated identity allowed to access this resource?".

### Contracts Between Easily Confused Interfaces

| Interface | Key method | Responsibility |
| --- | --- | --- |
| `ReactiveAuthenticationManager` | `authenticate(Authentication) -> Mono<Authentication>` | Verifies credentials and produces an authenticated result |
| `ReactiveUserDetailsService` | `findByUsername(String) -> Mono<UserDetails>` | Looks up user info for username/password authentication |
| `ServerAuthenticationConverter` | `convert(ServerWebExchange) -> Mono<Authentication>` | Converts an HTTP request into an authentication request |
| `AuthenticationWebFilter` | WebFilter | Connects request, converter, manager, and success/failure handlers |
| `SecurityWebFilterChain` | `matches(exchange)`, `getWebFilters()` | Defines the set of WebFilters applied to a request |
| `ReactiveAuthorizationManager<T>` | `check(Mono<Authentication>, T)` in 6.x API | Makes access-control decisions on the authenticated identity |

Do not equate `ReactiveUserDetailsService.findByUsername(...)` with `ReactiveAuthenticationManager.authenticate(...)`. Fetching a `UserDetails` **does not mean** the client's raw password is correct: password matching, account state checks, and producing a trusted authentication result are still required.

### Reactor `Context`, Not Servlet-Style ThreadLocal

In WebFlux, Spring Security stores `SecurityContext` information in the **Reactor Context** so downstream stages can access it reactively. After switching threads via a scheduler, a plain `ThreadLocal` is not sufficient to propagate the security context. If application code needs to read security info, use reactive APIs such as `ReactiveSecurityContextHolder.getContext()` in the pipeline; do not use Servlet-style `SecurityContextHolder.getContext()` as the source of truth in WebFlux.

## 5. Built-in Implementations

You do not need to write a manager from scratch for every problem.

| Implementation / option | Suitable scope |
| --- | --- |
| `UserDetailsRepositoryReactiveAuthenticationManager` | Username/password with `ReactiveUserDetailsService` and `PasswordEncoder` |
| `DelegatingReactiveAuthenticationManager` | Combines multiple managers; tries the next manager when an earlier branch returns empty |
| `JwtReactiveAuthenticationManager` | Authenticates JWTs in an appropriate resource server configuration |
| `OpaqueTokenReactiveAuthenticationManager` | Authenticates opaque bearer tokens via introspection in an appropriate configuration |
| `ReactiveAuthenticationManagerAdapter` | Bridges a synchronous `AuthenticationManager`; requires careful scheduler/blocking load considerations |
| Custom manager | Custom credential mechanism not yet supported by the framework; must follow the full contract and security policies |

In the hands-on section, `UserDetailsRepositoryReactiveAuthenticationManager` is the primary choice: it uses `ReactiveUserDetailsService` to look up users and `PasswordEncoder` to verify passwords. The custom portion only illustrates classifying tokens outside a manager's responsibility.

## 6. Complete Project: Spring Boot + Spring WebFlux + HTTP Basic

The example below targets **Java 17+**, **Spring Boot 3.3.5** with Spring Security 6.x managed by Spring Boot, and a compatible Gradle version. This is a **runnable** application with a complete file layout; the snippets in the theory section above are only illustrations.

### File Structure

```text
reactive-auth-manager-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/dev/example/authmanager/
    │   ├── ReactiveAuthManagerApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/dev/example/authmanager/
        └── AuthenticationManagerTests.java
```

`settings.gradle`:

```groovy
rootProject.name = 'reactive-auth-manager-demo'
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
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Use only `spring-boot-starter-webflux` for the web stack in this example. If you also add `spring-boot-starter-web`, Spring Boot usually prefers the Servlet configuration, making the WebFlux lesson difficult to verify accurately.

### 6.1. Startup Class

File `src/main/java/dev/example/authmanager/ReactiveAuthManagerApplication.java`:

```java
package dev.example.authmanager;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveAuthManagerApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveAuthManagerApplication.class, args);
    }
}
```

### 6.2. Declaring User Store, Encoder, and Authentication Manager

File `src/main/java/dev/example/authmanager/SecurityConfig.java`:

```java
package dev.example.authmanager;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
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
    ReactiveAuthenticationManager authenticationManager(
            ReactiveUserDetailsService users,
            PasswordEncoder encoder) {
        UserDetailsRepositoryReactiveAuthenticationManager manager =
                new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager authenticationManager) {
        return http
                .authenticationManager(authenticationManager)
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/admin").hasRole("ADMIN")
                        .anyExchange().authenticated()
                )
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
```

**Explanation by responsibility:**

1. `MapReactiveUserDetailsService` stores two sample users in memory and implements `ReactiveUserDetailsService`. Each record holds username, BCrypt hash, and roles.
2. `UserDetailsRepositoryReactiveAuthenticationManager` is given `ReactiveUserDetailsService` and `PasswordEncoder`. It is responsible for combining user lookup, credential verification, and account state checks per the framework implementation.
3. The bean returns the `ReactiveAuthenticationManager` interface itself; this shows callers only depend on the contract, not a concrete implementation.
4. `ServerHttpSecurity.authenticationManager(...)` sets the default manager for the security configuration. `httpBasic(...)` enables attempting username/password authentication extracted from HTTP Basic.
5. `/public` requires no login; `/admin` requires `ROLE_ADMIN`; all other URLs require authentication. `formLogin(form -> form.disable())` disables the form login page because the demo uses HTTP Basic.
6. The passwords `reader-pass` and `admin-pass` are **for learning/demo environments only**. `encode(...)` returns a BCrypt hash; passwords from requests must be matched with an appropriate encoder. Never log passwords or hashes.

With `.roles("ADMIN")`, Spring Security adds the `ROLE_` prefix; `hasRole("ADMIN")` checks the `ROLE_ADMIN` authority. In the `users` bean, admin has both `ROLE_READER` and `ROLE_ADMIN`.

**Why not write `password.equals(storedPassword)` yourself?** Because the stored password is a hash; checking must use `PasswordEncoder.matches(raw, encoded)`. Hand-rolling a username/password manager easily misses locked/disabled/expired account checks, timing behavior, or clearing raw credentials. Prefer the official implementation when suitable.

### 6.3. WebFlux Controller

File `src/main/java/dev/example/authmanager/DemoController.java`:

```java
package dev.example.authmanager;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping("/public")
    public Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/me")
    public Mono<String> me(Principal principal) {
        return Mono.just("user=" + principal.getName());
    }

    @GetMapping("/admin")
    public Mono<String> admin() {
        return Mono.just("admin-area");
    }
}
```

All handlers return `Mono<String>`, with no `block()` and no `subscribe()`. For authenticated requests, `Principal` is resolved by Spring WebFlux from the appropriate context.

## 7. Running and Observing HTTP Basic

Run from the `reactive-auth-manager-demo` directory, with compatible Gradle and JDK 17+:

```bash
gradle bootRun
```

If using Gradle Wrapper, run `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows. Once the application is running on `localhost:8080`, in another terminal:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u reader:reader-pass http://localhost:8080/me
curl -i -u reader:wrong-pass http://localhost:8080/me
curl -i -u reader:reader-pass http://localhost:8080/admin
curl -i -u admin:admin-pass http://localhost:8080/admin
```

Expected:

| Request | Notable HTTP status / body | Reason |
| --- | --- | --- |
| `GET /public`, no credentials | `200 OK`, `public` | `permitAll` rule |
| `GET /me`, no credentials | `401 Unauthorized` | Basic challenge, unauthenticated |
| `GET /me`, reader correct password | `200 OK`, `user=reader` | Manager emits valid authentication |
| `GET /me`, reader wrong password | `401 Unauthorized` | Manager emits authentication error; filter returns challenge |
| `GET /admin`, reader correct password | `403 Forbidden` | Authenticated but missing `ROLE_ADMIN` |
| `GET /admin`, admin correct password | `200 OK`, `admin-area` | Both authentication and authorization succeed |

The statuses/bodies above are **expected results for the sample configuration**. Headers and response details may vary by version/configuration. All commands use HTTP GET; for POST/PUT/DELETE, CSRF can affect the status separately.

> HTTP Basic only Base64-encodes username/password in the header; it **does not securely encrypt** credentials in transit. Only use plain HTTP on localhost for demos, and require HTTPS/TLS for real network traffic.

## 8. Testing the `Mono<Authentication>` Contract with `StepVerifier`

This is the core focus: testing **signals** rather than only looking at HTTP status codes. `reactor-test` provides `StepVerifier`, allowing you to assert `onNext`, `onComplete`, and `onError` without calling `block()`.

File `src/test/java/dev/example/authmanager/AuthenticationManagerTests.java`:

```java
package dev.example.authmanager;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class AuthenticationManagerTests {

    @Autowired
    ReactiveAuthenticationManager authenticationManager;

    @Autowired
    WebTestClient client;

    @Test
    void validCredentialsEmitAuthenticatedAuthenticationThenComplete() {
        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "reader", "reader-pass");

        assertFalse(request.isAuthenticated());

        StepVerifier.create(authenticationManager.authenticate(request))
                .assertNext(result -> {
                    assertTrue(result.isAuthenticated());
                    assertEquals("reader", result.getName());
                    assertTrue(result.getAuthorities().stream()
                            .anyMatch(a -> a.getAuthority()
                                    .equals("ROLE_READER")));
                })
                .verifyComplete();
    }

    @Test
    void badCredentialsProduceOnErrorNotEmpty() {
        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "reader", "wrong-pass");

        StepVerifier.create(authenticationManager.authenticate(request))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void unsupportedTokenCanProduceEmpty() {
        ReactiveAuthenticationManager usernamePasswordOnly = candidate -> {
            if (!(candidate instanceof UsernamePasswordAuthenticationToken)) {
                return Mono.empty();
            }
            return authenticationManager.authenticate(candidate);
        };

        Authentication unsupported =
                new TestingAuthenticationToken("robot", "opaque");

        StepVerifier.create(usernamePasswordOnly.authenticate(unsupported))
                .verifyComplete();
    }

    @Test
    void publicRequestNeedsNoCredentials() {
        client.get().uri("/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void missingCredentialsReturn401() {
        client.get().uri("/me")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void correctCredentialsReturnIdentity() {
        client.get().uri("/me")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("user=reader");
    }

    @Test
    void invalidCredentialsReturn401() {
        client.get().uri("/me")
                .headers(h -> h.setBasicAuth("reader", "wrong-pass"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedReaderLacksAdminRole() {
        client.get().uri("/admin")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminCanAccessAdminEndpoint() {
        client.get().uri("/admin")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin-area");
    }
}
```

Run tests:

```bash
gradle test
```

**Expected result:** **9 passing tests** when running the code and dependencies above. This outcome is inferred from the configuration and API contract, **not a claim that tests were executed in your repository**. Gradle may print many log lines, so do not assume verbatim stdout.

### What Is Being Verified?

- Test 1: The `Mono` emits exactly **one authenticated `Authentication`**, with trusted-source authority, then completes.
- Test 2: Wrong password emits `onError(BadCredentialsException)`; it does **not** turn into empty.
- Test 3: **An illustrative wrapper** handling only username/password returns `Mono.empty()` when encountering another token type. It demonstrates "unsupported", **without** assuming built-in username/password managers also return empty for every unfamiliar token.
- Six HTTP tests: authentication and authorization are properly wired to WebFlux HTTP Basic and the controller.

The empty test using `TestingAuthenticationToken` is **for unit tests only**. Do not put this token into a production login flow.

## 9. When Is `Mono.empty()` Useful?

Suppose a system has two distinct authentication mechanisms:
1. Manager A knows how to verify internal API key tokens.
2. Manager B knows how to verify username/password.

If A receives a token it does not support, A can return `Mono.empty()` to yield the decision to another component. When A receives the right API key type but the key is **wrong**, A must return `Mono.error(...)`; never treat a wrong key as "unknown" to evade the failure policy.

Decision table:

| Situation in a manager | Right | Avoid |
| --- | --- | --- |
| Token type is outside supported scope | `Mono.empty()` | Reporting "wrong password" before trying |
| Supported token type, valid credentials | `Mono.just(verifiedAuth)` | Setting `isAuthenticated` yourself without checking |
| Supported token type, wrong credentials | `Mono.error(BadCredentialsException)` | `Mono.empty()` |
| Infrastructure error, e.g. DB/identity provider unresponsive | Appropriate error signal and policy-aware handler | `onErrorResume(ex -> Mono.empty())` for all errors |
| User not found in username/password store | Authentication failure per policy | Returning success with a default principal |

### Combining Multiple Managers

`DelegatingReactiveAuthenticationManager` lets you try multiple delegates:

```java
ReactiveAuthenticationManager combined =
        new DelegatingReactiveAuthenticationManager(
                apiKeyManager, usernamePasswordManager);
```

This is an **illustrative snippet**: the two variables `apiKeyManager` and `usernamePasswordManager` must be defined for their respective mechanisms; import `org.springframework.security.authentication.DelegatingReactiveAuthenticationManager`. By default, when an earlier delegate returns **empty**, evaluation can continue with the next delegate. When a delegate emits an **error**, by default the error is propagated instead of silently swallowed. There is a `setContinueOnError(boolean)` option for special cases, but never enable it just to "let logins pass through".

Important: the final result of a manager chain depends on the delegation implementation, token types, delegate order, and the policy when nobody can authenticate. **Do not assume** a final empty automatically becomes `401` in every component; test real filter integration.

## 10. Custom Manager: Contract Shape and Constraints

If you have a specialized authentication method, you can implement the interface:

```java
// Illustrative snippet: example outside the runnable program in section 6.
final class DemoApiKeyAuthenticationManager
        implements ReactiveAuthenticationManager {

    private final ApiKeyVerifier verifier;

    DemoApiKeyAuthenticationManager(ApiKeyVerifier verifier) {
        this.verifier = verifier;
    }

    @Override
    public Mono<Authentication> authenticate(Authentication request) {
        if (!(request instanceof ApiKeyAuthenticationToken keyRequest)) {
            return Mono.empty();
        }

        return verifier.verify(keyRequest.getCredentials())
                .switchIfEmpty(Mono.error(
                        new BadCredentialsException("Invalid API key")))
                .map(verifiedIdentity ->
                        ApiKeyAuthenticationToken.authenticated(
                                verifiedIdentity));
    }
}
```

**This is typed illustrative Java pseudocode and does not compile standalone**: `ApiKeyVerifier`, `ApiKeyAuthenticationToken`, the `verifiedIdentity` type, and the methods are written to illustrate the interface to implement. Do not copy into a runnable file without defining them. A proper implementation must ensure:
- Distinguish **unsupported token type** from **wrong credentials**.
- Actually verify, check account state, and enforce lock/token-revocation policies.
- Load authorities from a trusted source; never copy them straight from requests or client headers.
- Never expose API keys, passwords, or access tokens in exceptions, logs, `toString()`, or tracing.
- Never emit `null`; never return `Mono.just(null)`.
- Never grant `isAuthenticated=true` based solely on self-declared data.
- Check thread-safety, timeouts, cancellation, load limits, and repeated calls.
- Only transfer verified results into `Authentication` and SecurityContext.

If you want to accept `X-API-Key` from an HTTP request, **a custom manager alone is not enough**. You also need a `ServerAuthenticationConverter` extracting the header to build the request token and an `AuthenticationWebFilter` configured with converter/manager/matching conditions, or a suitable Spring-supported authentication configuration. Do not take `ServerWebExchange` as direct input to `ReactiveAuthenticationManager.authenticate(...)`; the manager's parameter is `Authentication`.

## 11. Reactor: Errors, Schedulers, Retries, and Safety

### 11.1. When to Use `Mono.defer` or `fromCallable`?

A manager may rely on a truly reactive repository; in that case the query method can return a `Mono` from the driver without wrapping it again. If you must call a blocking SDK, defer the call and offload it to a scheduler meant for blocking work:

```java
// Illustrative snippet: legacyAuthClient is an existing blocking API.
Mono<LegacyResult> result = Mono
        .fromCallable(() -> legacyAuthClient.verify(rawCredential))
        .subscribeOn(Schedulers.boundedElastic());
```

Import `reactor.core.scheduler.Schedulers`. `LegacyResult` and `legacyAuthClient` are illustrative symbols. `fromCallable` defers the call until subscription; `subscribeOn(boundedElastic())` isolates blocking I/O from the event loop. **Lazy is not automatically non-blocking.** If an SDK is genuinely non-blocking, prefer its Reactor API instead of offloading everything to a scheduler.

Using `PasswordEncoder` can be CPU-intensive; Spring Security implementations have appropriate scheduling strategies for password verification. Do not call `passwordEncoder.matches(...)` on the event loop in a custom manager without considering computational cost.

### 11.2. Errors Must Be Represented Explicitly

```java
Mono<Authentication> rejected =
        Mono.error(new BadCredentialsException("Invalid credentials"));
```

Using an appropriate `AuthenticationException` helps the authentication filter/handler distinguish authentication failures from other errors. Do not return `Mono.empty()` when a password is wrong, and do not write `onErrorResume(ex -> Mono.just(authenticatedAdmin))` because that creates a vulnerability.

`BadCredentialsException` may be translated into HTTP `401` by the HTTP Basic flow, but `Mono.error(...)` is **not itself an HTTP response**. The HTTP status is decided by the filter, failure handler, entry point, and security configuration.

### 11.3. Retries Can Repeat Work

A cold `Mono` can re-run its logic on every subscription. `retry(...)` can also re-subscribe after an error. For authentication:
- Never automatically retry **wrong passwords**: it invites extra attempts, increases load, and distorts rate-limit policies.
- Bounded retries may be considered for certain transient infrastructure failures, but they must be separated from `AuthenticationException`, with explicit backoff and limits.
- If the manager performs side effects such as auditing, counting failed attempts, or locking accounts, you must account for idempotency and duplicate effects under retries.
- `timeout(...)` in Reactor does not guarantee actual cancellation of an underlying blocking I/O call inside a driver.

### 11.4. Do Not Use `block()` to Fetch `Authentication` in a WebFlux Handler

Wrong:

```java
// WRONG illustrative snippet, do not copy into a handler:
Authentication result = manager.authenticate(request).block();
```

Right is returning the publisher and composing reactively:

```java
// Illustrative snippet inside a method returning Mono<String>:
return manager.authenticate(request)
        .map(Authentication::getName);
```

In real WebFlux endpoints, you normally **do not call** the manager yourself from a controller to re-run authentication: let the WebFilter authenticate and read the verified principal. The right snippet above only illustrates Reactor composition, not a replacement for Spring Security filters.

### 11.5. Sensitive Information in `Authentication`

`Authentication.getCredentials()` may contain a password/token/raw secret before verification. Do not log the whole `Authentication` because `toString()`/diagnostic output from an implementation or monitoring library can leak data. After authentication, limit credential retention, never serialize this object into responses, and never embed raw secrets in `details`.

## 12. Separating Authentication from Authorization and HTTP Status

In the example:
- Logging in as `reader` with the right password -> manager returns a valid `Authentication` with `ROLE_READER`.
- `GET /admin` still receives **403**, because `hasRole("ADMIN")` is not satisfied.
- Logging in as `reader` with the wrong password -> manager reports **authentication failure**; HTTP Basic typically responds with **401**.
- `GET /public` without credentials still returns **200** because the rule allows public access. This **does not mean** the manager successfully authenticated an anonymous user.

Common point of confusion: `Authentication.isAuthenticated()` indicates the authentication result in terms of the token, whereas authorization uses authorities and rules. Never self-grant `ROLE_ADMIN` because the request URI contains `/admin`, and never treat `isAuthenticated()` as always sufficient for every endpoint.

With `AnonymousAuthenticationToken`, the system may create an authentication object representing an anonymous visitor in the security context; this does **not** mean they provided valid credentials. `.authenticated()` in security authorization understands a valid authentication context according to framework semantics rather than blindly reading a Boolean.

## 13. Common Errors and How to Fix Them

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| Wrong password yet manager returns `Mono.empty()` | Confusing "unsupported token type" with "authentication failed" | Return `Mono.error(BadCredentialsException)` |
| `401` despite valid credentials | `PasswordEncoder` does not match stored hash, wrong username, manager not wired into chain | Check encoder, `ReactiveUserDetailsService`, and `http.authenticationManager(...)` |
| `403` on `/admin` despite successful login | Result lacks `ROLE_ADMIN` authority | Separate authentication from authorization and check roles |
| `ClassCastException` when custom manager gets an unfamiliar token | Casting without checking type | Check `instanceof`, return empty if unsupported |
| WebFlux controller calls `block()` | Servlet-style thinking, can block event loop | Return `Mono`/`Flux` and let framework subscribe |
| `Mono.just(null)` throws an error | Reactor forbids `null` items | Use `Mono.empty()` properly or `Mono.justOrEmpty` for optional data (never to mask auth failure) |
| Constructing an authenticated token from a header username | Secret not verified; can grant fake access | Verify via trusted manager and backend authorities |
| Token/hard-coded secret appears in logs | Logging `Authentication`/exception/raw headers | Strip credentials from logs, apply redaction and secrets management |
| Custom manager runs blocking JDBC on event loop | Loses WebFlux concurrency | Use reactive driver or `fromCallable` + `boundedElastic` for blocking sources |
| Have `ReactiveUserDetailsService` but unclear on password verification | Confusing user lookup with authentication | Use `UserDetailsRepositoryReactiveAuthenticationManager` + `PasswordEncoder` |
| Empty test result for "wrong password" | Using `onErrorResume(... -> Mono.empty())` or broken fake manager logic | Write `expectError(BadCredentialsException.class)` test |
| Mixing `AuthenticationManager` (Servlet) and `ReactiveAuthenticationManager` | Different sync/reactive APIs | Prefer reactive manager; adapter only for controlled bridges |

### Checklist for a Custom Implementation

1. Handle only the exact `Authentication` type the manager supports.
2. Verify credentials against a trusted source, checking account/lock/revocation state.
3. Valid credentials -> emit **one** authenticated Authentication; unsupported -> empty; invalid -> error.
4. Never emit an authenticated auth if verification logic has not run.
5. Never trust client-supplied authorities.
6. Never allow blocking I/O to run on the event loop.
7. Minimize raw secrets lingering in memory/logs/responses.
8. Test all of success/error/empty and real HTTP integration.
9. Control retries, timeouts, cancellation, auditing, and rate limits.
10. Avoid rewriting password authentication when Spring Security's built-in implementation already fits.

## 14. Self-Check Questions

**1.** What type does `ReactiveAuthenticationManager.authenticate(...)` return?  
**Answer:** `Mono<Authentication>`.

**2.** Can `Mono.empty()` be used for a wrong password?  
**Answer:** No. It indicates the current manager cannot decide/does not support it; a wrong password must take the authentication error branch.

**3.** Once the user store returns `UserDetails`, can the user be considered authenticated?  
**Answer:** Not yet; credentials and user state must be checked and a valid result created.

**4.** What is the difference between `BadCredentialsException` and `403 Forbidden`?  
**Answer:** `BadCredentialsException` indicates authentication failure (HTTP Basic typically 401); `403` usually means authenticated but lacking permission, or caused by another mechanism like CSRF.

**5.** Why not construct `UsernamePasswordAuthenticationToken.authenticated(...)` straight from the request?  
**Answer:** Because that marks the state as authenticated without verifying it.

**6.** Why is testing with `StepVerifier` more valuable than just calling `.block()`?  
**Answer:** It verifies the exact sequence of success/complete/error signals, matching the Reactor contract directly.

**7.** If a manager only supports API keys and receives a `UsernamePasswordAuthenticationToken`, what should it emit?  
**Answer:** `Mono.empty()` to signal it does not handle that token type, when following a delegation strategy.

**8.** The manager returned an authenticated authentication; why is `GET /admin` still rejected?  
**Answer:** Authentication and authorization are two separate steps; the authority required by `hasRole("ADMIN")` must be present.

**9.** Is putting `.retry(3)` on all login errors appropriate?  
**Answer:** No; retrying wrong passwords is undesirable and can repeat side effects/rate limits.

**10.** What problem does `ReactiveSecurityContextHolder` solve?  
**Answer:** It lets reactive pipelines access the security context via the Reactor Context without depending on a fixed request thread.

### Hands-on Exercises

1. In the success test, also assert that `result.getAuthorities()` contains `ROLE_READER` and `result.isAuthenticated() == true`.
2. Add a test for a nonexistent username. Observe which `AuthenticationException` type the concrete implementation returns; do not expect the public response to distinguish a nonexistent user.
3. Create a simple `ReactiveAuthenticationManager` that accepts only `TestingAuthenticationToken` and returns `Mono.empty()` for `UsernamePasswordAuthenticationToken`. Test with `StepVerifier.verifyComplete()`.
4. Create an intentionally buggy manager: return `Mono.empty()` on wrong password. Write an `expectError(...)` test to prove the contract is broken; then fix it.
5. Protect the `GET /reader` endpoint with `hasRole("READER")`, verifying that both reader and admin can access it while a request without credentials gets 401.
6. In an advanced exercise, use `DelegatingReactiveAuthenticationManager` combining the username/password manager and a custom-token-only manager. Write three tests distinguishing valid, invalid, and unsupported tokens without leaking secrets.

## 15. Official Documentation

- [Spring Security API — ReactiveAuthenticationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html): success/empty/error return contract.
- [Spring Security API — UserDetailsRepositoryReactiveAuthenticationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/UserDetailsRepositoryReactiveAuthenticationManager.html): username/password manager.
- [Spring Security API — DelegatingReactiveAuthenticationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/DelegatingReactiveAuthenticationManager.html): composing multiple managers.
- [Spring Security API — AuthenticationWebFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html): converting HTTP requests into `Authentication` and handling results.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): configuring `@EnableWebFluxSecurity` and `SecurityWebFilterChain`.
- [Spring Security — Reactive Security Context](https://docs.spring.io/spring-security/reference/reactive/authentication.html): reactive authentication and context principles.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): using `StepVerifier` to verify signals.

**Takeaway:** `ReactiveAuthenticationManager` returns **one authenticated result** on success, **empty** when the manager has no decision, and **error** when authentication fails. Reading these three signals accurately is the foundation for integrating authentication in Spring Security reactive while keeping security policies sound.