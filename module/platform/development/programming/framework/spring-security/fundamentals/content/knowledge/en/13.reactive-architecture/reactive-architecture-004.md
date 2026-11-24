# ReactiveAuthenticationManager and Mono Return Contracts

> **Scope:** Spring Security in **Spring WebFlux (reactive)** applications, focusing on how `ReactiveAuthenticationManager` validates an `Authentication` and the exact meaning of `Mono<Authentication>` signals. Examples use Java 17+ and Spring Security 6.x/7.x.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the role of `ReactiveAuthenticationManager` in the WebFlux authentication flow and distinguish it from `ReactiveAuthorizationManager`, `ReactiveUserDetailsService`, and Servlet `AuthenticationManager`.
2. Distinguish the three valid outcomes of `authenticate`: **emit an `Authentication`**, **complete empty**, and **emit an error**.
3. Know when to use `Mono.empty()` versus `Mono.error(AuthenticationException)`, avoiding turning invalid credentials into “unsupported.”
4. Configure a manager backed by `ReactiveUserDetailsService`, test it with `StepVerifier`, and understand how results reach the WebFlux filter chain.
5. Recognize common pitfalls involving blocking, Reactor Context, swallowed errors, and improperly marking an `Authentication` object as authenticated.

## 2. Core Contract

`ReactiveAuthenticationManager` belongs to `org.springframework.security.authentication` and has a single functional method:

```java
@FunctionalInterface
public interface ReactiveAuthenticationManager {
    Mono<Authentication> authenticate(Authentication authentication);
}
```

The input is an `Authentication` to be verified: typically an **unauthenticated** token created by a credential-extraction layer (such as `UsernamePasswordAuthenticationToken.unauthenticated(username, password)`). The output is a `Mono<Authentication>` publisher representing **at most one** authentication result. The `Mono` type describes an asynchronous signal, not an already-materialized `Authentication`.

| Publisher outcome | Contract meaning | Example |
| --- | --- | --- |
| `onNext(authentication)` then `onComplete` | The manager authenticated successfully; the returned object must reflect a trustworthy principal/authorities and the appropriate authenticated state. | `Mono.just(authenticatedToken)` |
| `onComplete`, no `onNext` | The manager **cannot conclude** about this token, typically because the token type falls outside its responsibility. This is not a claim of “wrong password.” | `Mono.empty()` |
| `onError(error)` | The manager attempted authentication and **failed**, e.g., bad credentials or locked account; usually uses a subclass of `AuthenticationException`. Infrastructure errors can also travel on `onError` and must be classified/handled properly. | `Mono.error(new BadCredentialsException("Bad credentials"))` |

Key rules:

- **Token unsupported** by the current manager: return `Mono.empty()` so another orchestrating layer can try a matching manager.
- **Token supported, but credentials are wrong or account is invalid**: return `Mono.error(...)`; do not turn failure into `Mono.empty()`.
- **Success**: emit the verified `Authentication` object; never treat returning the unauthenticated input token as success.
- **Do not return `null`** in place of a `Mono` and do not create `Mono.just(null)`: Reactor forbids `null` values in `onNext`.
- **Do not return `Mono.never()`** when the manager cannot handle a token: it never completes, leaving pipelines hanging indefinitely; `Mono.empty()` is the valid “undecided” outcome.

A `Mono` can *complete empty* without an exception. Conversely, `onError` is a terminal failure signal with no `onComplete` after it. `AuthenticationException` can arise from credential checks or user-status checks; do not rely solely on HTTP status codes to reverse-infer all three states, because HTTP mapping also depends on the active filters/handlers.

### Comparison with the Synchronous API

| Servlet/blocking | WebFlux/reactive |
| --- | --- |
| `AuthenticationManager.authenticate(Authentication)` returns `Authentication` or throws `AuthenticationException` | `ReactiveAuthenticationManager.authenticate(Authentication)` returns `Mono<Authentication>`: value, empty, or error |
| Typically wired into `SecurityFilterChain` and Servlet filters | Wired into `SecurityWebFilterChain` and `WebFilter` |
| Traditional context is usually thread-bound | Reactive security context travels with the subscription's **Reactor Context** |

Do not take an `AuthenticationManager` from a Servlet configuration and assume you can invoke it directly and synchronously on the WebFlux event loop.

## 3. Where Does the Manager Sit in the WebFlux Flow?

```text
HTTP request
    |
    v
SecurityWebFilterChain (security WebFilters)
    |
    v
AuthenticationWebFilter (for the configured authentication mechanism)
    |-- matcher determines whether authentication should be attempted for the request
    |-- ServerAuthenticationConverter extracts credentials/token from the request
    |      \-- Mono.empty() at the converter step: no authentication attempt is made
    |
    v
ReactiveAuthenticationManager.authenticate(token)
    |-- non-empty Mono<Authentication> --> success handling,
    |                                      SecurityContext/Reactor Context
    |-- Mono.empty() ---------------------> no manager reached a decision
    |                                      (handling depends on the orchestrating layer)
    \-- Mono.error(...) ------------------> authentication failure handling
    |
    v
authorizeExchange / ReactiveAuthorizationManager
    |
    v
Handler or access-denied response
```

Breakdown by responsibility:

1. **`SecurityWebFilterChain`** is the security WebFilter chain selected for the request. This is a WebFlux construct, distinct from Servlet `SecurityFilterChain`.
2. **`ServerAuthenticationConverter`** extracts data from HTTP (e.g., Basic/Bearer header) and builds the token to authenticate. If the converter returns empty, there may be **no authentication attempt at all** for the request; that state differs from *a manager receiving a token and returning empty*.
3. **`ReactiveAuthenticationManager`** validates the token and returns one of the three signals above. It **authenticates identity**; it does not decide on its own whether the request may enter `/admin`.
4. Upon authentication success, the appropriate filters/handlers construct and place `SecurityContext` into the reactive stream; `ReactiveSecurityContextHolder` accesses the context via Reactor Context.
5. **Authorization** (such as `authorizeExchange().anyExchange().authenticated()` or role checks) runs according to configuration. An authenticated user can still be denied due to insufficient permissions.

Note: the diagram is a conceptual model for learning responsibility boundaries. Exact WebFilter order, selected handlers, and concrete responses depend on HTTP Basic, form login, resource server, custom filters, and application configuration. Do not assume that `Mono.empty()` from a manager automatically lets the request pass or guarantees 401 in every configuration.

## 4. Deep Dive into the Three Signals Through Java Code

### 4.1. Success: Emitting an Authentication

```java
Authentication authenticated =
        UsernamePasswordAuthenticationToken.authenticated(
                "alice",
                null,
                List.of(new SimpleGrantedAuthority("ROLE_READER"))
        );

Mono<Authentication> success = Mono.just(authenticated);
```

`authenticated(...)` should only be called **after the system has actually verified the credentials/token**. The snippet above only illustrates the shape of a trusted result; it **does not verify a password itself**. A successful instance typically retains the principal and granted authorities, and should avoid retaining secrets in credentials.

### 4.2. Undecided: Completing Empty

```java
ReactiveAuthenticationManager onlyUsernamePassword = request -> {
    if (!(request instanceof UsernamePasswordAuthenticationToken)) {
        return Mono.empty(); // This manager does not handle that token type
    }
    // The actual username/password branch must invoke the authentication system.
    return Mono.error(new BadCredentialsException("Bad credentials"));
};
```

Do not use `Mono.empty()` when the username/password is wrong. If the first manager swallows that error, a subsequent manager could be tried unexpectedly, skewing the security policy.

### 4.3. Failure: Emitting an Error

```java
Mono<Authentication> invalidPassword =
        Mono.error(new BadCredentialsException("Bad credentials"));
```

Normally, let `AuthenticationException` propagate to the authentication failure handling layer. With HTTP Basic, the appropriate failure handler typically produces a challenge/401; an authenticated request lacking permissions typically results in 403. The final status code can be customized; do not treat 401/403 as values returned directly by the manager itself.

### 4.4. Reactor Operators to Distinguish

- `switchIfEmpty(other)` triggers only when upstream **completes empty**. Use intentionally to select a fallback manager or turn an empty state into an error at a boundary requiring authentication.
- `onErrorResume(...)` handles **errors**, not `Mono.empty()`. Avoid blanket `onErrorResume(e -> Mono.empty())`: it hides invalid credentials or system failures.
- `flatMap(...)` composes work returning a `Mono` without calling `block()`.
- `Mono.defer(...)` defers task creation until subscription; `Mono.fromCallable(...)` is suited for wrapping synchronous operations, though blocking operations must be scheduled appropriately.
- `doOnNext`, `doOnError` are for observation; do not covertly mutate security state inside side effects.
- `retry()` is not a default policy for authentication: blindly retrying on wrong passwords or failing services can amplify load and produce hard-to-control behavior.

`Mono` is typically a *cold* publisher: declaring a pipeline does not mean a request to the user store has executed yet. WebFlux/Spring Security is the party subscribing during HTTP handling. Do not manually call `subscribe()` inside a manager or controller to “trigger” authentication, because a detached subscription can lose error handling and context.

## 5. Working Example: HTTP Basic in Spring WebFlux

The following example uses `UserDetailsRepositoryReactiveAuthenticationManager` instead of hand-rolling password verification logic. This manager relies on `ReactiveUserDetailsService` and `PasswordEncoder`.

**Setup:** create a Java 17+ compatible Spring Boot application with the two dependencies **Spring Reactive Web (WebFlux)** and **Spring Security** using Spring Initializr or an equivalent Boot project. Make sure you use WebFlux rather than adding Spring MVC in the same example. Source file `src/main/java/dev/demo/ReactiveAuthApplication.java`:

```java
package dev.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveAuthApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveAuthApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("demo123"))
                .roles("READER")
                .build();
        return new MapReactiveUserDetailsService(alice);
    }

    @Bean
    ReactiveAuthenticationManager reactiveAuthenticationManager(
            ReactiveUserDetailsService users, PasswordEncoder encoder) {
        var manager = new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http, ReactiveAuthenticationManager manager) {
        return http
                .authenticationManager(manager)
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @RestController
    static class DemoController {
        @GetMapping("/public")
        String publicPage() {
            return "public";
        }

        @GetMapping("/secure")
        String securePage() {
            return "secured";
        }
    }
}
```

Run the application with the project's build tool (e.g., `./gradlew bootRun` on macOS/Linux, `gradlew.bat bootRun` on Windows). HTTP commands to observe behavior:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/secure
curl -i -u alice:demo123 http://localhost:8080/secure
curl -i -u alice:wrong http://localhost:8080/secure
```

| Request | Expected outcome under the example's default configuration |
| --- | --- |
| `GET /public` without credentials | 200, body `public` due to `permitAll()` |
| `GET /secure` without credentials | 401 and HTTP Basic challenge |
| `GET /secure` with `alice:demo123` | 200, body `secured` |
| `GET /secure` with `alice:wrong` | 401 due to authentication failure |

Explanation:

- The HTTP Basic converter creates a token containing username/password when syntactically valid Basic credentials are present.
- The manager queries `ReactiveUserDetailsService` and uses `PasswordEncoder` to verify the encoded password; on success, the manager returns a trusted `Authentication`.
- The `authenticated()` rule only lets requests with an authenticated identity pass. `permitAll()` is an **authorization rule**, not a directive requiring the manager to authenticate every public request.
- Hardcoded accounts and demo passwords are for learning only. Real systems need a proper user store, secret management, HTTPS, brute-force protection, and error handling that does not leak account status.

**Limitation of the example:** `MapReactiveUserDetailsService` stores users in memory only, with no persistence. If using a real database, pick a reactive client/repository and avoid calling blocking JDBC directly on the event loop.

## 6. Testing the Contract with StepVerifier

To isolate **the meaning of the three signals** from HTTP, the following `src/test/java/dev/demo/ReactiveAuthenticationManagerContractTest.java` file builds a mock manager. It intentionally checks the string `good` to simulate outcomes; **never store or compare passwords this way in production**.

```java
package dev.demo;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReactiveAuthenticationManagerContractTest {

    private ReactiveAuthenticationManager demoManager() {
        return request -> {
            if (!(request instanceof UsernamePasswordAuthenticationToken)) {
                return Mono.empty();
            }
            if (!"good".equals(request.getCredentials())) {
                return Mono.error(new BadCredentialsException("Bad credentials"));
            }
            Authentication authenticated =
                    UsernamePasswordAuthenticationToken.authenticated(
                            request.getPrincipal(),
                            null,
                            List.of(new SimpleGrantedAuthority("ROLE_READER"))
                    );
            return Mono.just(authenticated);
        };
    }

    @Test
    void successfulAuthenticationEmitsExactlyOneValue() {
        var input = UsernamePasswordAuthenticationToken
                .unauthenticated("alice", "good");

        StepVerifier.create(demoManager().authenticate(input))
                .assertNext(result -> {
                    assertTrue(result.isAuthenticated());
                    assertEquals("alice", result.getName());
                    assertTrue(result.getAuthorities().stream()
                            .anyMatch(a -> a.getAuthority().equals("ROLE_READER")));
                })
                .verifyComplete();
    }

    @Test
    void unsupportedTokenCompletesWithoutValue() {
        var input = new TestingAuthenticationToken("alice", "good");

        StepVerifier.create(demoManager().authenticate(input))
                .verifyComplete();
    }

    @Test
    void invalidCredentialsFailWithAuthenticationException() {
        var input = UsernamePasswordAuthenticationToken
                .unauthenticated("alice", "wrong");

        StepVerifier.create(demoManager().authenticate(input))
                .expectError(BadCredentialsException.class)
                .verify();
    }
}
```

If using Gradle with Spring Boot WebFlux/Security dependencies, add the Reactor test dependency if starter-test does not already include it:

```groovy
dependencies {
    testImplementation 'io.projectreactor:reactor-test'
}
```

Run `./gradlew test` (or `gradlew.bat test` on Windows). All three tests should **pass**: test 1 proves one `onNext` followed by completion, test 2 proves no `onNext` with normal completion, and test 3 proves `onError` of type `BadCredentialsException`. This is a contract test; it does not claim that the entire filter chain or real user data has been tested.

For HTTP integration testing, use `WebTestClient` to send requests with no credentials, wrong credentials, and valid credentials; verify status/headers and actual route access. Testing at both layers prevents confusing “the manager returns the right signal” with “the whole application enforces the policy.”

## 7. Combining Multiple Managers Properly

An application may support multiple authentication methods, such as username/password and bearer tokens. `DelegatingReactiveAuthenticationManager` tries the configured managers and uses the **first non-empty result**. In Spring Security 6.5/7.x, an error from a delegate is **not** treated as an empty result by default to automatically try the next manager (`continueOnError` defaults to `false`).

Token-type selection pattern:

```java
ReactiveAuthenticationManager usernamePasswordOnly =
        token -> token instanceof UsernamePasswordAuthenticationToken
                ? realUsernamePasswordManager.authenticate(token)
                : Mono.empty();

ReactiveAuthenticationManager combined =
        new DelegatingReactiveAuthenticationManager(
                bearerTokenManager,
                usernamePasswordOnly
        );
```

The snippet above is an **integration pattern**, not a standalone compilable file: `realUsernamePasswordManager` and `bearerTokenManager` must be supplied from your application configuration; the example only illustrates the role of `Mono.empty()` for unsupported token types. For concrete mechanisms such as OAuth2 Resource Server, prefer Spring Security's standard configuration so the framework selects the proper converter/manager instead of wiring the protocol manually.

Do not enable continue-on-error just to “let it try the next one”: once a manager recognizes a credential type and concludes it is invalid, trying another manager can shift trust boundaries. If business logic genuinely needs fallback, you must explicitly define token types, error types, precedence, observable behavior, and test attack paths.

## 8. Reactor Context, Threads, and Blocking Operations

`ReactiveSecurityContextHolder` reads authentication data from the Reactor Context bound to the **subscription**; do not assume it resides in a stable `ThreadLocal` across `flatMap`, `publishOn`, etc.

A handler/service running inside a request authenticated by Spring Security can read:

```java
Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName());
}
```

This is an **illustrative method snippet**, requiring imports for `reactor.core.publisher.Mono` and `org.springframework.security.core.context.ReactiveSecurityContextHolder` in the enclosing class. When no `SecurityContext` is present, the publisher can complete empty. Do not call `block()` or ad-hoc `subscribe()` to extract the name; return `Mono` up to the WebFlux layer.

Performance-wise, “returning a `Mono`” **does not automatically make blocking work non-blocking**. For example, querying JDBC, calling a synchronous SDK, or running CPU-intensive hashing directly on the event loop will stall other requests. Prefer reactive APIs for I/O; when a synchronous operation is unavoidable, wrap the task appropriately with `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`, monitor load, and limit concurrency. `ReactiveAuthenticationManagerAdapter` can adapt a synchronous `AuthenticationManager` to the reactive API; it is a compatibility bridge, not something that turns a blocking data source truly reactive.

Illustrative example of scheduling a blocking function **for demonstration**, not a complete manager implementation:

```java
Mono<Boolean> matchesPassword(String raw, String encoded,
                              PasswordEncoder encoder) {
    return Mono.fromCallable(() -> encoder.matches(raw, encoded))
            .subscribeOn(Schedulers.boundedElastic());
}
```

Requires importing `PasswordEncoder`, `Mono`, and `Schedulers`. In real projects, prefer the framework-provided manager because it already handles details such as account verification, password encoding, and exception structure. Do not create a separate thread/scheduler per request.

## 9. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Returning `Mono.empty()` on wrong password | May trigger a fallback manager and make security logic hard to control | For determined bad credentials, emit `BadCredentialsException` via `Mono.error` |
| Returning `Mono.just(inputToken)` while still unauthenticated | Grants false trust or leaves principal/authorities inconsistent | Construct a trusted token only after successful verification |
| Returning `null` or `Mono.just(null)` | Violates Reactor contract, causing runtime errors | Always return a non-null `Mono`; use `Mono.empty()` when the token type cannot be handled |
| `onErrorResume(e -> Mono.empty())` for all errors | Swallows credential errors and infrastructure failures | Catch only policy-approved error types and preserve meaningful authentication errors |
| `block()` inside a manager/`WebFilter` | Stalls the event loop, cuts throughput, or triggers blocking errors | Use reactive composition; isolate blocking calls on a suitable scheduler |
| Manual `subscribe()` inside a manager | Work detaches from the HTTP chain; errors and Reactor Context become hard to control | Return the publisher for Spring Security to subscribe |
| Mixing `HttpSecurity` with `ServerHttpSecurity` | Mismatches Servlet/WebFlux models; configuration does not apply as expected | Use `SecurityWebFilterChain`, `ServerHttpSecurity`, and the corresponding reactive APIs |
| Logging passwords, bearer tokens, or detailed stack traces in responses | Leaks credentials or internal details | Redact sensitive data, write safe audit logs, and return consistent error responses |
| Assuming `Mono.empty()` from a manager means a public request | Confuses authentication with authorization; can create vulnerabilities | Enforce authorization independently via `authorizeExchange`, and test protected routes |
| Wrapping authentication in unbounded `retry()` | Amplifies load, prolongs failures, and masks root causes | Retry only idempotent infrastructure calls under bounded policies, never bad credentials |

## 10. Self-Check

1. A manager supporting only `UsernamePasswordAuthenticationToken` receives an unfamiliar bearer token. What should it return? **`Mono.empty()`** if it truly does not know how to handle that token type.
2. The manager supports username/password, but the password is wrong. What should it return? **`Mono.error(new BadCredentialsException(...))`**.
3. Does a `Mono.just(authenticated)` result mean the `/admin` endpoint will succeed? **No**. After authentication, the request still has to pass authorization rules.
4. How does a converter returning `Mono.empty()` differ from a manager returning `Mono.empty()`? **The converter did not produce a token to try**, whereas the manager received a token and reached no conclusion; the HTTP outcome depends on the filter chain.
5. Why should you not call `block()` to retrieve `SecurityContext`? Because the request follows a reactive flow and context belongs to the subscription; blocking/thread assumptions can break semantics and hurt performance.
6. What minimum contract cases should you test? Success emits exactly one trustworthy `Authentication`, unsupported token types complete empty, bad credentials emit `AuthenticationException`, and real endpoints obey the HTTP security policy.

## 11. Official Documentation for Reference

- [ReactiveAuthenticationManager — API contract](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html)
- [AuthenticationWebFilter — WebFlux authentication flow](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html)
- [WebFlux Security configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Reactive HTTP request authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Project Reactor — Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)

**Takeaway:** `ReactiveAuthenticationManager` does not return “true/false.” It returns a publisher with **three distinct outcomes**: a valid `Authentication`, **empty when undecided**, or **error when authentication fails**. That distinction is the foundation for safely composing multiple managers and letting the filter chain interpret authentication state accurately.
