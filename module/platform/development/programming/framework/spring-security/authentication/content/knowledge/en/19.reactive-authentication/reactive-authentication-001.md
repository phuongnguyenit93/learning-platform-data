# ReactiveAuthenticationManager and the Mono<Authentication> Contract

## 1. What Problem Does ReactiveAuthenticationManager Solve?

In a **Spring WebFlux** application, Spring Security needs to verify credentials supplied via HTTP Basic, form login, a Bearer token, or a custom mechanism. Instead of assuming the result is available immediately on the calling thread, Spring Security uses the **ReactiveAuthenticationManager** interface: it takes an `Authentication` object and returns a Reactor publisher of type `Mono<Authentication>`.

Core definition:

~~~java
package org.springframework.security.authentication;

import org.springframework.security.core.Authentication;
import reactor.core.publisher.Mono;

@FunctionalInterface
public interface ReactiveAuthenticationManager {
    Mono<Authentication> authenticate(Authentication authentication);
}
~~~

This is a **condensed API signature to explain the contract**, not a file to copy into your application source. Do not redeclare this interface yourself: Spring Security already provides it.

**One-sentence meaning:** `ReactiveAuthenticationManager` returns **a successful authentication result**, **no conclusion**, or **an error** via three distinct Reactor signal types. Spring Security WebFlux relies on those signals to decide how to handle the request next.

Differences from traditional Servlet design:

| Aspect | Servlet security | WebFlux security |
| --- | --- | --- |
| Manager contract | `AuthenticationManager.authenticate(Authentication)` | `ReactiveAuthenticationManager.authenticate(Authentication)` |
| Return type | `Authentication` or throws exception | `Mono<Authentication>` |
| Execution | Usually processed synchronously on the servlet request thread | Publisher subscribed as part of the reactive pipeline |
| Protocol filter | Servlet `Filter`, `SecurityFilterChain`, `HttpSecurity` | Reactive `WebFilter`, `SecurityWebFilterChain`, `ServerHttpSecurity` |
| Security context | Usually accesses `SecurityContextHolder` (thread-bound) | `ReactiveSecurityContextHolder` in the **Reactor Context** |
| Testing | JUnit + MockMvc | JUnit + StepVerifier + WebTestClient |
| What to avoid | Overloading arbitrary logic inside providers | `block()`, manual `subscribe()`, blocking the Netty event loop, using ThreadLocal as the primary context source |

Do not mix up the APIs: `HttpSecurity`/`UsernamePasswordAuthenticationFilter` belong to Servlet; `ServerHttpSecurity`/`AuthenticationWebFilter` belong to WebFlux. Even if an application has both libraries on the classpath, that does not mean the two filter stacks automatically blend together.

## 2. Three Outcomes That Must Be Distinguished

Spring Security's public contract specifies three cases:

| Reactive signal | Example | Correct meaning | What must **not** be inferred |
| --- | --- | --- | --- |
| `onNext(authentication)` then `onComplete()` | `Mono.just(authenticated)` | **Authentication succeeded**; returns an appropriate, verified `Authentication` with a trusted principal and authorities. | Returning non-null alone is not enough: an unauthenticated token must not be treated as a successful login. |
| `onComplete()` only | `Mono.empty()` | **The manager cannot determine** whether it handles this request; it may be meant for another manager. | It does not mean wrong password, nonexistent account, or system error. |
| `onError(exception)` | `Mono.error(new BadCredentialsException(...))` | **Authentication failed or the authentication service errored**. | It does not mean every error returns HTTP 401; HTTP mapping is decided by WebFlux filters/handlers. |

Read-only examples:

~~~java
// A. Success: there is an actually verified Authentication.
Mono<Authentication> ok = Mono.just(authenticatedToken);

// B. Not responsible: do not emit any Authentication.
Mono<Authentication> unsupported = Mono.empty();

// C. Reject wrong credentials: emit an error signal.
Mono<Authentication> invalid = Mono.error(
    new BadCredentialsException("Invalid credentials")
);
~~~

The three variables above are **illustrative snippets**, where `authenticatedToken` is assumed to have been safely created by the verifying component. Never copy `Mono.just(authenticatedToken)` and mark a client-supplied token as authenticated.

### 2.1. Success: A Trusted Authentication

A `Mono` publisher emits **at most one** item, then completes. When authentication succeeds, `Authentication` typically contains:

- Principal: the verified user, service account, or identity.
- Authorities: roles/scopes/permissions sourced from the server or verified credentials.
- `isAuthenticated() == true` per the contract of a valid implementation.
- Credentials cleared or not retained when no longer needed.

The following example is **the result-creation step after credentials have already been checked**, not a complete program:

~~~java
Authentication verified =
    UsernamePasswordAuthenticationToken.authenticated(
        userDetails,
        null,
        userDetails.getAuthorities()
    );

return Mono.just(verified);
~~~

The `authenticated(...)` method **does not check the password itself**. Calling it before verification or taking authorities from the client's JSON request is a critical vulnerability: you have promoted an untrusted token into an authenticated result.

### 2.2. Empty: “Inconclusive”, Not “Anonymous Login”

A manager may handle a specific token type, such as `ApiKeyAuthenticationToken`. If it encounters `UsernamePasswordAuthenticationToken`, that manager is not responsible for checking it. Returning `Mono.empty()` allows a coordinating mechanism to try another manager.

~~~java
@Override
public Mono<Authentication> authenticate(Authentication input) {
    if (!(input instanceof MyApiKeyAuthenticationToken)) {
        return Mono.empty();
    }
    return verifyApiKey((MyApiKeyAuthenticationToken) input);
}
~~~

This is **Java pseudocode**; `MyApiKeyAuthenticationToken` and `verifyApiKey` must be defined by the application. The key point is distinguishing **unsupported token type** from **an API key owned by this manager that is invalid**. An invalid API key must produce an authentication error, not return empty to fall back to a weaker source.

Do not use:

~~~java
return Mono.just(null); // WRONG: Reactor does not allow null onNext.
~~~

In Reactor, `Mono.just(null)` throws `NullPointerException` when creating the publisher. `Mono.justOrEmpty(null)` creates an empty publisher, but you should not use it as a “shortcut” to hide all errors or every missing username.

### 2.3. Error: Credential Recognition Failures and System Errors

Example:

~~~java
return Mono.error(new BadCredentialsException("Invalid credentials"));
~~~

This is how to signal incorrect credentials when the manager **is responsible for authenticating this token type**. For locked/disabled accounts:

~~~java
return Mono.error(new LockedException("Account locked"));
// Or DisabledException, AccountExpiredException,
// CredentialsExpiredException when matching the actual cause.
~~~

When the authentication system is temporarily unable to operate:

~~~java
return Mono.error(new AuthenticationServiceException(
    "Authentication backend unavailable", originalCause));
~~~

In the last snippet, `originalCause` is the original exception caught at the integration boundary. It is an **illustrative snippet**, not advice to catch every `Exception` and convert it into a single error type. An infrastructure failure does not mean the user entered the wrong password.

**Boundary:** `Mono.error(...)` emits a reactive error signal. A Java `throw new BadCredentialsException(...)` inside `Mono.defer(...)` is also converted by Reactor into `onError` upon subscription, but using `Mono.error` is clearer for flow control and testing.

## 3. From Publisher to Signal: Why You Must Not Think of Mono as an Authentication

`Mono<Authentication>` is **not** an already-resolved `Authentication`. A publisher is typically a description of work that executes only when subscribed to:

~~~text
Create publisher: manager.authenticate(request)
          |
          | Does not necessarily query DB or hash password yet
          |
     Publisher Mono<Authentication>
          |
       subscribe()
          |
          +-- onNext(auth) -> onComplete
          |
          +-- onComplete without onNext
          |
          +-- onError(AuthenticationException/...)
~~~

In a normal WebFlux request, **the framework is the subscriber**. Whoever writes the manager only assembles operators and returns the publisher, without manually calling `subscribe()`, `block()`, or `toFuture().get()` inside filters or managers.

### 3.1. Mono.defer When Work Must Be Created at Subscription Time

~~~java
@Override
public Mono<Authentication> authenticate(Authentication request) {
    return Mono.defer(() -> {
        if (!supportsRequest(request)) {
            return Mono.empty();
        }
        return verifyReactive(request);
    });
}
~~~

This is **illustrative code**; `supportsRequest` and `verifyReactive` are implemented by the application. `Mono.defer` ensures the decision inside the lambda happens when a subscription occurs. It is useful when building the publisher has side effects, needs per-subscription state, or depends on timing policy.

Keep in mind:

- A `Mono` can be a cold publisher; **multiple subscriptions may repeat** queries/verifications and cause side effects. Do not accidentally subscribe twice to the same login just to “capture logs”.
- `Mono.just(...)` emits a value already computed at call time; use `Mono.defer`/`fromCallable` when you want lazy evaluation.
- `Mono.empty()` does not emit a `null` value; it emits **no `onNext` at all**.
- `Mono.error(...)` is not a normal return value; if unhandled, the error signal propagates to upstream operators and handlers.
- `Flux<Authentication>` is not the contract's return type; authenticating a single request must not emit a list of multiple users.

### 3.2. flatMap, map, and switchIfEmpty

A proper pattern:

~~~java
return reactiveUsers.findByUsername(username)
    .switchIfEmpty(Mono.error(
        new BadCredentialsException("Invalid credentials")))
    .flatMap(user -> verifyPasswordThenCreateAuthentication(user, rawPassword));
~~~

This is a fragment requiring two custom dependencies/methods. These operators mean:

- `findByUsername` is a reactive publisher that may emit a user or complete empty.
- `switchIfEmpty` **turns “username not found” into an authentication failure**, because this manager is responsible for username/password authentication.
- `flatMap` is used when the next step also returns a publisher.
- `map` is used for synchronous non-blocking transformations. Do not call `map(user -> verifyPasswordBlocking(...))` directly on the Netty event loop.

Placing `switchIfEmpty` in the wrong spot can cause provider fallback bugs. For instance, `.onErrorResume(error -> Mono.empty())` at the end of a pipeline turns **wrong password, locked account, and infrastructure errors** into “manager undecided”: this can open a bypass path if a later manager in the chain accepts the request.

## 4. How Synchronous AuthenticationManager Differs from ReactiveAuthenticationManager

The two contracts have similar names:

~~~java
// Servlet / synchronous
Authentication authenticate(Authentication request)
        throws AuthenticationException;

// WebFlux / reactive
Mono<Authentication> authenticate(Authentication request);
~~~

With synchronous `ProviderManager`, a provider can return `null` when it cannot handle a token; with `ReactiveAuthenticationManager`, the equivalent signal in the contract is **`Mono.empty()`**, not `null` and not `Mono.just(null)`.

Some practical points:

| Question | Synchronous Servlet | Reactive WebFlux |
| --- | --- | --- |
| Authenticated? | Returns `Authentication` | `Mono` emits `Authentication` |
| Cannot decide / unsupported? | Provider returns `null` per provider contract | Manager returns `Mono.empty()` |
| Invalid credentials? | Throws `AuthenticationException` | `Mono.error(AuthenticationException)` |
| Thread context | `SecurityContextHolder` typically ThreadLocal-based | `ReactiveSecurityContextHolder` via Reactor Context |
| Calling user store | Can use synchronous JDBC | Should use a reactive repository/client; avoid blocking the event loop |
| Multiple backends | `AuthenticationProvider` ordering in `ProviderManager` | Delegating `ReactiveAuthenticationManager` or manager resolver |
| HTTP filter | `UsernamePasswordAuthenticationFilter`, `BasicAuthenticationFilter` | `AuthenticationWebFilter` and WebFlux security filters |

Do not simply wrap with `Mono.just(blockingAuthenticationManager.authenticate(...))`: the expression inside `Mono.just(...)` **executes synchronously** before the publisher is even returned. It can block the event loop even though the outer return type is `Mono`.

If you must call a legacy synchronous `AuthenticationManager`, Spring Security provides `ReactiveAuthenticationManagerAdapter` with a scheduler mechanism; this is a bridge solution, not something that turns a blocking dependency into truly non-blocking I/O. Prefer a reactive design from the ground up when the backend supports it.

## 5. Where Does a WebFlux Request Go?

High-level flow for HTTP Basic:

~~~text
HTTP GET /api/me
Authorization: Basic ...
          |
          v
Spring WebFlux + Spring Security WebFilter chain
          |
          v
AuthenticationWebFilter / basic authentication support
          |
          +-- Does SecurityWebFilterChain match URL?
          |
          +-- ServerAuthenticationConverter reads request
          |       |
          |       +-- Mono.empty()
          |       |     No matching credentials found;
          |       |     do not call manager for this attempt
          |       |
          |       +-- Authentication request token
          |             |
          |             v
          |    ReactiveAuthenticationManager.authenticate(...)
          |             |
          |             +-- onNext(Authentication): success path
          |             +-- onComplete(empty): no decision
          |             +-- onError(...): failure path
          |
          v
ReactiveSecurityContextHolder / success-failure handling
          |
          v
Authorization WebFilter / ServerAccessDeniedHandler
          |
          v
Handler/controller if permitted
~~~

**Do not confuse the two different kinds of empty:**

- `ServerAuthenticationConverter.convert(exchange)` returning empty means **no authentication request token was created**, e.g., missing Basic header: the authentication filter may skip authentication and continue the filter chain.
- `ReactiveAuthenticationManager.authenticate(token)` returning empty means **there is a token to evaluate, but the manager could not reach a decision**. How `AuthenticationWebFilter` or a coordinator handles this depends on the implementation and security configuration; it is **not guaranteed** that empty from a manager always results in anonymous, 401, or “trying every next manager”.

After a result is produced, `ServerAuthenticationSuccessHandler` or `ServerAuthenticationFailureHandler` handles the request. The response may be 401/403/redirect or an API status depending on the configured entry point, authorization rules, and exception handling. The manager does not write the HTTP response directly.

### 5.1. Reactor Context Holds the Identity

In WebFlux, reactive operators may execute across multiple threads; do not rely on the regular ThreadLocal `SecurityContextHolder` as the guaranteed source of request identity.

~~~java
Mono<String> username = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName);
~~~

This is a fragment meant to run **inside a pipeline** that has a Reactive Security Context. If called standalone outside a request without a context, the publisher may be empty. Spring Security populates the context into the Reactor Context for protected requests.

Standalone illustrative test example:

~~~java
Authentication verified = UsernamePasswordAuthenticationToken.authenticated(
    "student", null, List.of(new SimpleGrantedAuthority("ROLE_USER"))
);

Mono<String> name = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName)
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(verified));

StepVerifier.create(name)
    .expectNext("student")
    .verifyComplete();
~~~

This is an **illustrative test snippet** requiring Spring Security, Reactor, and Reactor Test imports; `verified` is a synthetic test token, not advice to elevate real user privileges. Reactor Context propagates along the subscription, rather than being replaced by `ThreadLocal`, static global variables, or setting `SecurityContextHolder.setContext` inside an async task and expecting it to propagate elsewhere.

## 6. Rules for Implementing a Custom Manager

Before writing code, clearly define the scope:

1. **Which Authentication type is handled?** For example, `UsernamePasswordAuthenticationToken` for HTTP Basic.
2. **When the type is unsupported?** Return `Mono.empty()`.
3. **When in scope, but username/password is wrong?** Return `Mono.error(new BadCredentialsException(...))`.
4. **When the account is locked/disabled?** Return the proper `AccountStatusException` such as `LockedException`/`DisabledException`.
5. **When the backend errors?** Classify the authentication/service error; do not turn it into empty or wrong password.
6. **When successful?** Return a new authenticated `Authentication` with server-sourced principal/authorities, without keeping the raw password.
7. **Are there any blocking calls?** Use reactive DB/APIs when available; CPU-intensive password hash verification must be scheduled on an appropriate scheduler.
8. **Who subscribes and handles HTTP?** The framework/caller, not the manager subscribing to itself.
9. **What if there are multiple managers?** Design routing/fallback transparently; do not treat `onError` as a signal to “try a weaker backend”.
10. **Source of security context?** Reactor Context, not storing authentication in global variables or ThreadLocal across operators.

### 6.1. Do Not Let a Nonexistent Username Become Empty

The following example is **semantically wrong** if the manager is responsible for username/password:

~~~java
return users.findByUsername(username)
    .flatMap(user -> checkAndAuthenticate(user, password));
// If the user does not exist, the result is Mono.empty() => INCORRECT
// when the credentials belong to this manager and are rejected.
~~~

Correct code must turn an empty lookup into an error:

~~~java
return users.findByUsername(username)
    .switchIfEmpty(Mono.error(
        new BadCredentialsException("Invalid credentials")))
    .flatMap(user -> checkAndAuthenticate(user, password));
~~~

These snippets are fragments; `users`, `username`, `password`, and `checkAndAuthenticate` must exist in the actual class. To clients, avoid distinguishing “username does not exist” from “wrong password” in detailed messages to prevent user enumeration. Consider techniques to reduce timing leaks if the risk profile warrants it.

### 6.2. Do Not Block the Event Loop with Synchronous I/O

Anti-patterns:

~~~java
// WRONG: executes synchronous query when CREATING the publisher.
return Mono.just(jdbcRepository.findByUsername(username));

// WRONG: waits for reactive result directly inside the request.
UserDetails user = reactiveUsers.findByUsername(username).block();

// WRONG: subscribes detached from the authentication pipeline.
reactiveUsers.findByUsername(username).subscribe(user -> audit(user));
return Mono.empty();
~~~

Solutions:

- Prefer `ReactiveUserDetailsService` with a reactive backend.
- If you must integrate a blocking API, use `Mono.fromCallable(...)` with a suitable scheduler, and **return the publisher**.
- Password hashing like BCrypt is relatively CPU-intensive; do not run it directly on the Netty event loop. Consider a dedicated scheduler or `Schedulers.parallel()` depending on load, measure throughput, and bound concurrency.
- Do not fetch secrets from an external service using synchronous calls on the event loop.
- Do not apply `parallel()` unconditionally everywhere: scheduling must match whether the work is CPU-bound, blocking I/O, or asynchronous I/O.

## 7. Spring Boot 3.x / Java 17+ Example: HTTP Basic Authentication Manager

This is a minimal WebFlux application so learners can verify all three signals. It uses HTTP Basic because it readily produces a `UsernamePasswordAuthenticationToken` without writing a custom JSON login or cookie session flow. It uses an in-memory demo user only—never deploy hardcoded passwords to production.

Structure:

~~~text
src/main/java/com/example/reactiveauth/
  ReactiveAuthApplication.java
  LocalReactiveAuthenticationManager.java
  ReactiveSecurityConfig.java
  WhoAmIController.java

src/test/java/com/example/reactiveauth/
  LocalReactiveAuthenticationManagerTest.java
  ReactiveAuthHttpTest.java
~~~

### 7.1. Dependencies

In a Spring Boot 3.x Gradle project with plugins and dependency management:

~~~groovy
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

This snippet goes into `build.gradle` of a project that already has the Spring Boot plugin, repositories, and Java 17+. **Do not add `spring-boot-starter-web`** to the demo because it can cause the app to default to Servlet MVC and make the WebFlux filter setup mismatch. If both stacks are needed, explicitly decide the application type and security chain rather than relying on classpath accidents.

### 7.2. ReactiveAuthApplication.java

~~~java
package com.example.reactiveauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveAuthApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveAuthApplication.class, args);
    }
}
~~~

### 7.3. LocalReactiveAuthenticationManager.java

The code below implements all three signals:

- Does not handle other token types → `Mono.empty()`.
- Wrong username/password → `Mono.error(BadCredentialsException)`.
- Valid authentication → `Mono.just(Authentication)`.

~~~java
package com.example.reactiveauth;

import org.springframework.security.authentication.AccountExpiredException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.CredentialsExpiredException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public final class LocalReactiveAuthenticationManager
        implements ReactiveAuthenticationManager {

    private final ReactiveUserDetailsService users;
    private final PasswordEncoder passwordEncoder;

    public LocalReactiveAuthenticationManager(
            ReactiveUserDetailsService users,
            PasswordEncoder passwordEncoder) {
        this.users = users;
        this.passwordEncoder = passwordEncoder;
    }

    @Override
    public Mono<Authentication> authenticate(Authentication request) {
        // defer: logic runs when the framework subscribes.
        return Mono.defer(() -> {
            // This manager only handles username/password.
            if (!(request instanceof UsernamePasswordAuthenticationToken)) {
                return Mono.empty();
            }

            String username = request.getName();
            Object credentials = request.getCredentials();

            if (username == null || username.isBlank()
                    || !(credentials instanceof String rawPassword)
                    || rawPassword.isBlank()) {
                return Mono.error(new BadCredentialsException(
                    "Invalid username or password"));
            }

            // Lookup from ReactiveUserDetailsService may be empty.
            return users.findByUsername(username)
                .switchIfEmpty(Mono.error(new BadCredentialsException(
                    "Invalid username or password")))
                .flatMap(user -> {
                    // Distinguish account status from an incorrect password.
                    if (!user.isEnabled()) {
                        return Mono.error(new DisabledException(
                            "Account disabled"));
                    }
                    if (!user.isAccountNonLocked()) {
                        return Mono.error(new LockedException(
                            "Account locked"));
                    }
                    if (!user.isAccountNonExpired()) {
                        return Mono.error(new AccountExpiredException(
                            "Account expired"));
                    }
                    if (!user.isCredentialsNonExpired()) {
                        return Mono.error(new CredentialsExpiredException(
                            "Credentials expired"));
                    }

                    // BCrypt is CPU-bound work; offload from the
                    // Netty event loop. Benchmark/tune scheduler under load.
                    return Mono.fromCallable(() ->
                            passwordEncoder.matches(
                                rawPassword, user.getPassword()))
                        .subscribeOn(Schedulers.parallel())
                        .flatMap(matches -> {
                            if (!matches) {
                                return Mono.error(new BadCredentialsException(
                                    "Invalid username or password"));
                            }

                            Authentication verified =
                                UsernamePasswordAuthenticationToken.authenticated(
                                    user, null, user.getAuthorities());

                            return Mono.just(verified);
                        });
                });
        });
    }
}
~~~

**Exact flow breakdown:**

1. `Mono.defer(...)` does not turn blocking I/O into reactive I/O by itself, but it creates the work at subscription time.
2. Check the class first: if the manager does not handle another token type, return `Mono.empty()` without throwing `ClassCastException`.
3. Blank or non-String credentials in the demo are rejected; in production, the converter/manager must enforce the protocol's exact credential type.
4. `ReactiveUserDetailsService.findByUsername(...)` returns empty if the user does not exist; `switchIfEmpty(Mono.error(...))` is required to make the credential failure explicit.
5. Account status is checked **before** the password so locked/disabled accounts do not proceed.
6. BCrypt `matches` runs on a scheduler meant for CPU computation instead of occupying the Netty event loop; real load and concurrency should be measured. Spring Security's standard manager also has its own scheduling handling, so prefer the standard implementation unless custom logic is needed.
7. After successful verification, create a new `Authentication` with authorities from the server's `UserDetails`.
8. Credentials in the authenticated result are set to `null`; do not log the raw password or return it to the client.
9. Outage errors from `ReactiveUserDetailsService` are not converted into `BadCredentialsException`/empty in this code; the application must configure observability, error mapping, and resilience at dependency boundaries.
10. No manual `subscribe()` or `block()`: WebFlux's request flow subscribes via the framework.

**Demo limitations:** an in-memory user store is for learning. Production systems typically use standard managers/frameworks such as `UserDetailsRepositoryReactiveAuthenticationManager`, a JWT manager, or custom integrations; they need account lockout, rate limiting, auditing, hashing policy, latency budgets, and tests.

### 7.4. ReactiveSecurityConfig.java

~~~java
package com.example.reactiveauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService reactiveUsers(PasswordEncoder encoder) {
        return new MapReactiveUserDetailsService(
            User.withUsername("student")
                .password(encoder.encode("demo-pass"))
                .roles("READER")
                .build()
        );
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            ReactiveUserDetailsService users,
            PasswordEncoder encoder) {
        return new LocalReactiveAuthenticationManager(users, encoder);
    }

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager manager) {
        return http
            .authorizeExchange(exchange -> exchange
                .pathMatchers("/public").permitAll()
                .pathMatchers("/api/me").hasRole("READER")
                .anyExchange().denyAll()
            )
            .httpBasic(basic -> basic.authenticationManager(manager))
            .formLogin(form -> form.disable())
            .build();
    }
}
~~~

Explanation:

- `@EnableWebFluxSecurity` and `SecurityWebFilterChain` belong to the **reactive** model; there is no `HttpSecurity` or servlet filter.
- `MapReactiveUserDetailsService` holds one demo user while implementing `ReactiveUserDetailsService`, exercising the proper API.
- The custom `ReactiveAuthenticationManager` is wired directly into the HTTP Basic authentication mechanism via `httpBasic(...authenticationManager(manager))`.
- `/public` is open, `/api/me` requires `ROLE_READER`, and other URLs are denied.
- Form login is disabled so the demo uses HTTP Basic only. Requests without Basic credentials will not be redirected to a session-based form login.
- CSRF is not disabled by default in the example; all demo endpoints are GET. If you add POST endpoints and browsers automatically send credentials/cookies, evaluate CSRF separately rather than disabling it just because the app uses WebFlux.

### 7.5. WhoAmIController.java

~~~java
package com.example.reactiveauth;

import java.util.Map;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class WhoAmIController {

    @GetMapping("/public")
    public Mono<Map<String, String>> publicPage() {
        return Mono.just(Map.of("message", "public"));
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(authentication -> Map.of(
                "username", authentication.getName(),
                "authenticated",
                Boolean.toString(authentication.isAuthenticated())
            ));
    }
}
~~~

Here `ReactiveSecurityContextHolder` reads the identity from the request's Reactor Context. The controller does not parse the Basic header a second time and does not create a new `Authentication`. The endpoint has already been authorized by `SecurityWebFilterChain` before entering the controller.

### 7.6. Running and HTTP Expectations

In a Gradle project with the wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Try with a local client:

~~~bash
# Public endpoint: 200
curl -i http://localhost:8080/public

# Without Authorization: 401/Basic challenge
curl -i http://localhost:8080/api/me

# Valid credentials: 200
curl -i -u student:demo-pass http://localhost:8080/api/me

# Wrong credentials: 401
curl -i -u student:wrong http://localhost:8080/api/me

# Nonexistent username: 401
curl -i -u nobody:demo-pass http://localhost:8080/api/me
~~~

Expected success JSON payload:

~~~json
{
  "username": "student",
  "authenticated": "true"
}
~~~

This is the **expected response inferred from the code**, not stdout/HTTP logs from an actual run. `curl -u` can expose passwords in process arguments or command history. Use dummy passwords on localhost and HTTPS for external environments. Server-side Base64 decoding of HTTP Basic is not security encryption; Basic must run over TLS.

**Do not conclude** that `ReactiveAuthenticationManager` directly returns HTTP 401: the manager emits `Mono.error(BadCredentialsException)`, and the HTTP Basic filter/failure handler/entry point produces the response.

## 8. JUnit 5 + StepVerifier: Testing All Three Signals Precisely

`StepVerifier` verifies the exact `onNext` count, exception type, and publisher completion. It is far better than comparing `Mono.toString()` or calling `block()` and losing empty/error semantics.

File `src/test/java/com/example/reactiveauth/LocalReactiveAuthenticationManagerTest.java`:

~~~java
package com.example.reactiveauth;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class LocalReactiveAuthenticationManagerTest {

    private final PasswordEncoder encoder = new BCryptPasswordEncoder(4);

    private final ReactiveUserDetailsService users =
        new MapReactiveUserDetailsService(
            User.withUsername("student")
                .password(encoder.encode("demo-pass"))
                .roles("READER")
                .build()
        );

    private final LocalReactiveAuthenticationManager manager =
        new LocalReactiveAuthenticationManager(users, encoder);

    private static Authentication input(String name, String password) {
        return UsernamePasswordAuthenticationToken.unauthenticated(
            name, password);
    }

    @Test
    void emitsAuthenticatedValueWhenPasswordIsCorrect() {
        StepVerifier.create(manager.authenticate(
                input("student", "demo-pass")))
            .assertNext(result -> {
                assertTrue(result.isAuthenticated());
                assertEquals("student", result.getName());
                assertTrue(result.getAuthorities().stream()
                    .anyMatch(a -> "ROLE_READER".equals(a.getAuthority())));
            })
            .verifyComplete();
    }

    @Test
    void completesEmptyForUnsupportedAuthenticationClass() {
        Authentication other = new TestingAuthenticationToken(
            "student", "other-credential");

        StepVerifier.create(manager.authenticate(other))
            .verifyComplete(); // No onNext.
    }

    @Test
    void rejectsWrongPasswordAsErrorNotEmpty() {
        StepVerifier.create(manager.authenticate(
                input("student", "wrong")))
            .expectError(BadCredentialsException.class)
            .verify();
    }

    @Test
    void rejectsUnknownUsernameAsErrorNotEmpty() {
        StepVerifier.create(manager.authenticate(
                input("nobody", "demo-pass")))
            .expectError(BadCredentialsException.class)
            .verify();
    }

    @Test
    void rejectsBlankCredential() {
        StepVerifier.create(manager.authenticate(
                input("student", "")))
            .expectError(BadCredentialsException.class)
            .verify();
    }

    @Test
    void rejectsDisabledAccountWithoutAcceptingCorrectPassword() {
        ReactiveUserDetailsService disabledUsers =
            new MapReactiveUserDetailsService(
                User.withUsername("disabled")
                    .password(encoder.encode("demo-pass"))
                    .disabled(true)
                    .roles("READER")
                    .build()
            );

        LocalReactiveAuthenticationManager disabledManager =
            new LocalReactiveAuthenticationManager(
                disabledUsers, encoder);

        StepVerifier.create(disabledManager.authenticate(
                input("disabled", "demo-pass")))
            .expectError(DisabledException.class)
            .verify();
    }

    @Test
    void doesNotConvertBackendErrorIntoBadCredentials() {
        ReactiveUserDetailsService failedStore =
            name -> reactor.core.publisher.Mono.error(
                new org.springframework.security.authentication
                    .AuthenticationServiceException(
                        "Credential store unavailable",
                        new IllegalStateException("Simulated outage"))
            );

        LocalReactiveAuthenticationManager failedManager =
            new LocalReactiveAuthenticationManager(
                failedStore, encoder);

        StepVerifier.create(failedManager.authenticate(
                input("student", "demo-pass")))
            .expectError(
                org.springframework.security.authentication
                    .AuthenticationServiceException.class)
            .verify();
    }
}
~~~

**Notes when reading the tests:**

- `verifyComplete()` without `expectNext` verifies that the publisher **emits no value** and completes normally. It is only used for unsupported token types, never for wrong passwords.
- `assertNext(...)` both verifies there is exactly one result and inspects principal/authorities. `verifyComplete()` confirms there is no extra value and no error.
- `expectError(...)` asserts that a real error is emitted. If the manager accidentally returns `Mono.empty()`, the test fails.
- The disabled account test ensures “correct password” alone does not grant access; account status still matters.
- The failing store test simulates an `AuthenticationServiceException` with a cause: the manager does not turn an outage into wrong username/password.
- BCrypt strength 4 is only for fast testing; production must use a compliant cost factor balancing performance and security.
- `TestingAuthenticationToken` is used as an unsupported token type, not as a credential sent over real HTTP Basic.

**Do not call `block()` in production handlers to “simplify testing”.** `StepVerifier` in tests is the right tool to subscribe and assert signals.

## 9. Testing WebFlux Over HTTP with WebTestClient

Manager unit tests do not prove that `AuthenticationWebFilter`, the entry point, authorization, and Reactor Context are wired properly. Add an integration test using `WebTestClient`.

File `src/test/java/com/example/reactiveauth/ReactiveAuthHttpTest.java`:

~~~java
package com.example.reactiveauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive
    .AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveAuthHttpTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointDoesNotNeedCredentials() {
        client.get()
            .uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("public");
    }

    @Test
    void basicCredentialsProduceAuthenticatedPrincipal() {
        client.get()
            .uri("/api/me")
            .headers(headers -> headers.setBasicAuth(
                "student", "demo-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.username").isEqualTo("student")
            .jsonPath("$.authenticated").isEqualTo("true");
    }

    @Test
    void wrongPasswordGetsUnauthorized() {
        client.get()
            .uri("/api/me")
            .headers(headers -> headers.setBasicAuth(
                "student", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void unknownUsernameGetsUnauthorized() {
        client.get()
            .uri("/api/me")
            .headers(headers -> headers.setBasicAuth(
                "nobody", "demo-pass"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void missingCredentialsAreNotAutomaticallyAuthenticated() {
        client.get()
            .uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

Run:

~~~bash
./gradlew test --tests com.example.reactiveauth.LocalReactiveAuthenticationManagerTest
./gradlew test --tests com.example.reactiveauth.ReactiveAuthHttpTest
~~~

Windows:

~~~powershell
.\gradlew.bat test --tests com.example.reactiveauth.LocalReactiveAuthenticationManagerTest
.\gradlew.bat test --tests com.example.reactiveauth.ReactiveAuthHttpTest
~~~

These are **expected tests based on the source**; no Gradle run has been executed in this article. When the project compiles and tests pass, Gradle typically prints `BUILD SUCCESSFUL`; other log lines may vary by version.

Because the example uses HTTP Basic in WebFlux, when credentials are missing or wrong, the default `AuthenticationEntryPoint` configuration typically produces 401 and a Basic challenge. However, that is **not a rule for every manager**: JSON APIs or custom filters may need a `ServerAuthenticationFailureHandler` to map system errors to 503 or another response without leaking stack traces to the client.

## 10. DelegatingReactiveAuthenticationManager: Ordering and Fallback

When a system has multiple credential types or multiple user sources, Spring Security provides `DelegatingReactiveAuthenticationManager`. It takes multiple `ReactiveAuthenticationManager` instances and coordinates them.

### 10.1. Default Rules

With two managers A and B:

~~~text
A.authenticate(token)
     |
     +-- Mono.just(Authentication) → stop, return success
     |
     +-- Mono.empty() → try B
     |
     +-- Mono.error(...) → stop by default, do not try B

B.authenticate(token)
     |
     +-- Mono.just(Authentication) → success
     +-- Mono.empty()              → no result yet
     +-- Mono.error(...)            → error
~~~

`setContinueOnError(false)` is the default. Since Spring Security 6.3, `setContinueOnError(true)` allows the manager to continue looking for a result even if a previous delegate emitted an error. This is a **security decision**: if a strong manager returns `BadCredentialsException`, another manager could accept the same identity through a weaker mechanism. Do not enable it carelessly just to ignore errors.

### 10.2. Code Illustrating the Mechanism

~~~java
ReactiveAuthenticationManager first =
    request -> Mono.empty();

ReactiveAuthenticationManager second =
    request -> Mono.just(
        UsernamePasswordAuthenticationToken.authenticated(
            "fallback-user",
            null,
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        )
    );

DelegatingReactiveAuthenticationManager delegates =
    new DelegatingReactiveAuthenticationManager(first, second);
~~~

This is a **fragment** in which `second` deliberately “accepts” to illustrate **ordering**. **Never use a manager that accepts without verifying credentials in production.**

The following test illustrates the logic:

~~~java
StepVerifier.create(delegates.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
            "anyone", "example")))
    .assertNext(result ->
        assertEquals("fallback-user", result.getName()))
    .verifyComplete();
~~~

This test snippet requires `delegates` from the fragment above along with imports. It shows that `Mono.empty()` from A gives B a chance.

### 10.3. Errors Do Not Fall Back by Default

~~~java
ReactiveAuthenticationManager rejecting = request ->
    Mono.error(new BadCredentialsException("Denied by first manager"));

ReactiveAuthenticationManager fallback = request ->
    Mono.just(UsernamePasswordAuthenticationToken.authenticated(
        "unexpected-user",
        null,
        List.of(new SimpleGrantedAuthority("ROLE_USER"))
    ));

DelegatingReactiveAuthenticationManager guarded =
    new DelegatingReactiveAuthenticationManager(rejecting, fallback);

// With default configuration, BadCredentialsException is emitted.
StepVerifier.create(guarded.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
            "student", "wrong")))
    .expectError(BadCredentialsException.class)
    .verify();
~~~

If `guarded.setContinueOnError(true)` is called, the same test can turn into **fallback success**, which is precisely the bypass risk scenario to analyze. This example deliberately uses a dangerous fallback to explain semantics, not as a recommended real configuration.

### 10.4. Route by Token Type/Endpoint Instead of Mixing Ambiguous Fallbacks

Easier-to-control options:

- `/api/**` uses a JWT/Bearer manager and rejects invalid tokens.
- `/login/**` uses a username/password manager.
- Custom API key mechanisms use a dedicated token class and dedicated manager.
- Choose `ReactiveAuthenticationManagerResolver<ServerWebExchange>` or matcher-based chains when routing per request, instead of a blanket `onErrorResume` for all errors.

If one token type is supported by multiple managers and each can return a successful Authentication, there must be a clear **ownership policy** so a weaker backend cannot open access to an account already rejected by a stronger backend.

## 11. Common Anti-Patterns

### 11.1. Using Mono.empty for Wrong Password

~~~java
if (!passwordMatches) {
    return Mono.empty();  // SEMANTICALLY WRONG.
}
~~~

Consequence: callers may interpret this as “manager does not handle it” and invoke another fallback. It must be `Mono.error(new BadCredentialsException(...))`.

### 11.2. Using Mono.just(null)

~~~java
return Mono.just(null);  // Reactor does not support null onNext.
~~~

`null` is not an empty success event. Return `Mono.empty()` when **inconclusive**, and do not let `null` mask errors.

### 11.3. Mono.just with a Blocking Call

~~~java
return Mono.just(legacyAuthManager.authenticate(request));
~~~

The expression `legacyAuthManager.authenticate(...)` runs **immediately when constructing the Mono**, potentially blocking the Netty event loop. Use a reactive manager, a controlled adapter/scheduler, or `Mono.fromCallable(...).subscribeOn(...)` if a synchronous API cannot be avoided.

### 11.4. Blocking, Subscribing Manually, or Using ThreadLocal

~~~java
Authentication a = manager.authenticate(request).block();
manager.authenticate(request).subscribe(this::saveGlobalUser);
SecurityContextHolder.getContext().setAuthentication(a);
~~~

This is an **anti-pattern** in WebFlux requests. Detaching subscriptions or relying on ThreadLocal can lose the Reactor Context and cause cross-request authorization bugs. Return the publisher and let WebFlux drive the chain.

### 11.5. Catching All Errors and Passing Through

~~~java
return backendAuthenticate(input)
    .onErrorResume(error -> Mono.empty());
~~~

A DB outage, locked account, or bad credentials all get collapsed into “unknown”. If there is a fallback, requests may be accepted against policy. Only use `onErrorResume` for specific exception types and security-reviewed outcomes.

### 11.6. Using onErrorReturn with an Authenticated Token

~~~java
return verify(input)
    .onErrorReturn(UsernamePasswordAuthenticationToken.authenticated(
        "guest", null, List.of()));
~~~

Wrong and dangerous: the manager turns **every failure** into an Authentication success for a principal the client never proved. If anonymous access is needed, let Spring Security WebFlux provide anonymous processing and matching authorization; do not fake authentication inside a manager.

### 11.7. Putting Raw Credentials in the Result or Logs

Do not keep passwords/plaintext in `getCredentials()` inside long-lived objects, logs, JSON responses, or telemetry. Do not log Basic headers/JWTs/API keys. Set credentials to `null` in the result when not needed.

### 11.8. Assuming Spring Verifies isAuthenticated After Code Sets It to True

`Authentication.isAuthenticated` is not a password check. A custom manager must **perform full verification itself** before creating an authenticated result. Do not trust self-declared user-supplied roles or usernames without verification.

### 11.9. Testing Only HTTP 401 While Forgetting Mono Signals

The same HTTP 401 can come from a converter emitting no token, a manager throwing `BadCredentialsException`, an entry point, or an access policy. Test both at the **StepVerifier manager** level and the **WebTestClient HTTP** level to know which path actually ran.

### 11.10. Using ReactiveAuthenticationManager Instead of ReactiveAuthorizationManager

Authentication determines **who is calling**; authorization decides **whether the authenticated caller is permitted to perform the action**. `ReactiveAuthorizationManager` and `authorizeExchange` belong to authorization. Do not put role rules inside the manager to replace authorization policy: the manager can populate accurate authorities, but endpoints must still enforce checks.

## 12. System Errors: Do Not Let Wrong Password Mask an Outage

Beyond `BadCredentialsException`, distinguish:

| Scenario type | Appropriate signal | HTTP response the application may design |
| --- | --- | --- |
| Wrong username/password | `Mono.error(BadCredentialsException)` | 401, generic message |
| Username in manager's scope but not found | Usually `Mono.error(BadCredentialsException)` | 401, do not leak user existence |
| Token type outside manager's scope | `Mono.empty()` | Depends on router / other manager / entry point |
| Locked account | `Mono.error(LockedException)` | No automatic fallback; status per policy |
| Disabled account | `Mono.error(DisabledException)` | No automatic fallback |
| Credential database timeout | `Mono.error(AuthenticationServiceException)` or classified infrastructure error | Possibly 503 with a custom handler |
| Remote API returns invalid data | Reactive error preserving cause, fail closed | Do not grant roles/Authentication |
| Valid | `Mono.just(Authentication)` | Proceed to authorization; may be 200 or 403 |

**Do not claim that Spring Security returns 503 by default for every `AuthenticationServiceException`.** WebFlux filters/error handlers decide HTTP mapping. In production, log infrastructure errors with a correlation ID (without credentials), plus metrics, redacted tracing, timeouts, and circuit breakers/rate limiting where appropriate.

A classification pattern at the integration boundary (pseudocode):

~~~java
return remoteIdentityService.verify(input)
    .onErrorMap(RemoteIdentityUnavailableException.class,
        ex -> new AuthenticationServiceException(
            "Identity provider unavailable", ex));
~~~

Map **only** true inability-to-verify failures; do not catch `BadCredentialsException`, `LockedException`, or arbitrary `RuntimeException` and turn them into `Mono.empty()`. `remoteIdentityService` and `RemoteIdentityUnavailableException` are hypothetical names, not a standalone program.

## 13. Testing Laziness, Cancellation, Timeouts, and Schedulers

A reactive manager can return the right publisher type yet still behave poorly in production if operators are misplaced.

### 13.1. Laziness

~~~java
AtomicInteger calls = new AtomicInteger();

ReactiveUserDetailsService spy = username ->
    Mono.defer(() -> {
        calls.incrementAndGet();
        return Mono.just(userDetails);
    });

Mono<Authentication> result =
    new LocalReactiveAuthenticationManager(spy, encoder)
        .authenticate(
            UsernamePasswordAuthenticationToken.unauthenticated(
                "student", "demo-pass")
        );

// Before subscribing, calls may still be 0
// because the spy performs its side effect inside defer.
assertEquals(0, calls.get());

StepVerifier.create(result)
    .expectNextCount(1)
    .verifyComplete();

assertEquals(1, calls.get());
~~~

This is a **test fragment**, not a standalone runnable file: `userDetails` must have a valid password hash and imports. It demonstrates per-subscription effects, not a claim that every external publisher is always lazy.

### 13.2. Timeout/Cancellation

When a backend does not respond, requests should not wait indefinitely. Reasonable timeouts can be placed on the reactive client or pipeline, along with classifying timeouts as service errors. However:

- `timeout(...)` produces an error signal; it must not silently become `BadCredentialsException` or empty.
- Cancellation stops the subscription at the Reactor level, though remote operations may need proper cancellation support.
- Indiscriminate retries of password verification or credential POSTs can cause load spikes, lockouts, and duplicate side effects.
- Never return an authenticated result if verification timed out or was cancelled.
- Test time-based operators with `StepVerifier.withVirtualTime` when the code supports a virtual scheduler; do not use long `Thread.sleep` calls to test timeouts.

### 13.3. Matching Schedulers to Workload Nature

- Truly non-blocking reactive DB/HTTP clients: no need to wrap every operation in `boundedElastic()`.
- CPU-intensive password hashing: can use `Schedulers.parallel()` or a dedicated bounded scheduler, benchmarked under load.
- Legacy JDBC/blocking calls: temporarily use `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`, but cap concurrency and prioritize migrating to reactive.
- Do not use `Schedulers.immediate()` for heavy BCrypt if that causes it to run on the event loop.
- Do not create a new scheduler per request, as it easily causes thread leaks/overhead.

## 14. Safely Combining Multiple Credential Sources

A WebFlux request may carry a session cookie, HTTP Basic, a Bearer token, or an API key. `ReactiveAuthenticationManager` only handles **the Authentication object passed to it by the filter/converter**; it does not decide on its own which credential type “wins” the request.

Determine each step in order:

1. Which `SecurityWebFilterChain` matches the URL; only the selected chain runs.
2. Which authentication filters/converters are present and whether they detect credentials.
3. Which `ReactiveAuthenticationManager` or manager resolver is used.
4. What the manager returns (`onNext`/empty/error) and how fallback is configured.
5. After authentication, which roles/scopes the authorization policy checks.
6. Which Reactor Context or repository stores the security context; whether subsequent requests still need credentials.

Prefer routing mechanisms cleanly by endpoint/token type. When an invalid token has been presented, **do not automatically fall back** to a cookie or weaker source unless the product has a security-proven policy. `DelegatingReactiveAuthenticationManager.setContinueOnError(true)` can be valid in specialized scenarios, but you must test “manager A rejects, manager B accepts” before allowing deployment.

## 15. QA Matrix for ReactiveAuthenticationManager

| Case | Input | Expected signal | Additional checks |
| --- | --- | --- | --- |
| RA-01 | Supported token type, valid credentials | `onNext(Authentication)` + complete | principal, authorities, `isAuthenticated` |
| RA-02 | Unsupported token type | complete without value | `Mono.empty()`, no error |
| RA-03 | Wrong password | `onError(BadCredentialsException)` | must not become empty |
| RA-04 | Nonexistent username in responsible store | `onError(BadCredentialsException)` | no user enumeration leak |
| RA-05 | Null/blank credentials | `onError(BadCredentialsException)` | no unintended `NullPointerException` |
| RA-06 | Disabled user | `onError(DisabledException)` | no access granted even with right password |
| RA-07 | Locked user | `onError(LockedException)` | no fallback |
| RA-08 | User credentials expired | `onError(CredentialsExpiredException)` | account status enforced |
| RA-09 | Backend unavailable | `onError(AuthenticationServiceException)` or explicit error | preserve cause, do not turn into BadCredentials |
| RA-10 | First manager empty, second succeeds | onNext from second manager | `DelegatingReactiveAuthenticationManager` in order |
| RA-11 | First manager errors, default delegating | error, does not call second manager | fail-closed policy |
| RA-12 | `continueOnError(true)` | second manager may run after error | check bypass risk |
| RA-13 | Not yet subscribed | deferred side effects do not execute | test laziness |
| RA-14 | Valid HTTP Basic | `WebTestClient` receives 200 + principal | accurate context and roles |
| RA-15 | Wrong HTTP Basic | receives 401 per entry point | no stack trace/password leak |
| RA-16 | No Basic header | not authenticated | converter may emit empty |
| RA-17 | Manager emits onNext but lacks ROLE | authorization 403 | authentication differs from authorization |
| RA-18 | Runtime outage in user store | does not grant Authentication | proper observability and status |
| RA-19 | Subscription cancelled/timed out | does not emit fake success | timeout/cancel policy |
| RA-20 | Reactive pipeline switches threads | context remains intact | Reactor Context, not ThreadLocal |

The most important test suite for the **contract** is RA-01/02/03: the exact same `authenticate(...)` method emitting **three distinct terminal behaviors**. The HTTP tests RA-14/15/16 prove that real requests hit the right WebFlux filter/manager rather than unit-testing a class left unwired from configuration.

## 16. Conclusion

**ReactiveAuthenticationManager does not return an Authentication immediately: it returns a Mono describing the authentication process.** The contract requires strictly distinguishing:

- **`Mono.just(authenticated)`**: an actually verified result with principal/authorities from a trusted source.
- **`Mono.empty()`**: the manager cannot decide / is not responsible for that specific token; useful for delegating to another manager, **not** for wrong passwords.
- **`Mono.error(AuthenticationException)`**: credentials were rejected or the authentication process errored; must preserve specific exception semantics.
- **`DelegatingReactiveAuthenticationManager`**: continues on empty, **stops on error by default**; enabling continue-on-error is a risk-bearing decision.
- **WebFlux**: `SecurityWebFilterChain`, `AuthenticationWebFilter`, Reactor Context, and Spring Security handlers govern how requests flow and HTTP responses are produced.
- **Proper implementation**: no `block()`, no manual `subscribe()`, no `Mono.just(null)`, no ThreadLocal as context source, no careless fallback when credentials are invalid.
- **Proper testing**: use `StepVerifier` to assert onNext/empty/error and `WebTestClient` to verify HTTP flow, authorization, entry point, and actual principal.

Whenever possible, **prefer Spring Security's standard managers** for username/password, JWT, or opaque tokens; write a custom `ReactiveAuthenticationManager` only when you have a specialized protocol or data source. That keeps the contract clear, testable, and lower risk.

### References

- Spring Security 6.5 API — ReactiveAuthenticationManager: https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html
- Spring Security 6.5 API — DelegatingReactiveAuthenticationManager: https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/authentication/DelegatingReactiveAuthenticationManager.html
- Spring Security 6.5 API — AuthenticationWebFilter: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html
- Spring Security 6.5 API — ServerHttpSecurity.HttpBasicSpec: https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.HttpBasicSpec.html
- Spring Security 6.5 API — AbstractUserDetailsReactiveAuthenticationManager: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/authentication/AbstractUserDetailsReactiveAuthenticationManager.html
- Spring Security Reference — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security Reference — Reactive Authentication: https://docs.spring.io/spring-security/reference/reactive/authentication/index.html
- Spring Security Reference — Reactive Authorization / Reactor Context: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Project Reactor — Mono Javadoc: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Reactor Test — StepVerifier: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html
