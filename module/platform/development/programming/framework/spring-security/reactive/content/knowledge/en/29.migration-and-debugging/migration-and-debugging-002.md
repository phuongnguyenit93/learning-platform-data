# Migrating from UserDetailsService and AuthenticationManager to Reactive Contracts

## Context, Goals, and Scope

In a Spring MVC (Servlet) application, you typically use `UserDetailsService` and `AuthenticationManager` to authenticate usernames and passwords. When migrating to **Spring WebFlux / Spring Security Reactive**, the corresponding API pair is `ReactiveUserDetailsService` and `ReactiveAuthenticationManager`. This is a change in **return contract, error signaling, execution timing, and security context**, not just wrapping `Mono` around method signatures.

This lesson belongs to **Spring Security – reactive / Migration and debugging**. After completing it, you will be able to:

1. Compare the Servlet and Reactive contracts and distinguish the responsibilities of user lookup versus password validation.
2. Migrate username/password authentication to `ReactiveUserDetailsService` and `UserDetailsRepositoryReactiveAuthenticationManager` without changing password, authority, or account-status semantics.
3. Choose between a **pure reactive migration** and a **temporary bridge** to synchronous `UserDetailsService`/`AuthenticationManager` using `boundedElastic`.
4. Wire the manager into `SecurityWebFilterChain`, read authentication from Reactor Context, test contracts with `StepVerifier`, and verify HTTP behavior using `WebTestClient` or curl.
5. Distinguish between user-not-found errors, bad passwords, unsupported token types, storage failures, blocking calls, and misconfigured Servlet/WebFlux stacks.

Examples target **Java 17+, Spring Boot 3.x, Spring Security 6.x, and Reactor**, using username/password authentication. OAuth2 Resource Server, JWT, and OIDC have dedicated managers/filters and are not automatically turned into username/password repositories merely because the application uses WebFlux.

## 1. Mapping the Two Security Contracts

| Responsibility | Servlet / synchronous | WebFlux / reactive | Migration implication |
| --- | --- | --- | --- |
| User lookup | `UserDetailsService.loadUserByUsername(String)` returns `UserDetails` or throws `UsernameNotFoundException` | `ReactiveUserDetailsService.findByUsername(String)` returns `Mono<UserDetails>` | Never return `null`; emit the user when found, typically `Mono.empty()` when absent |
| Credential verification | `AuthenticationManager.authenticate(Authentication)` returns `Authentication` or throws `AuthenticationException` | `ReactiveAuthenticationManager.authenticate(Authentication)` returns `Mono<Authentication>` | Success = emit authenticated token; failure = `onError`; cannot decide = `Mono.empty()` |
| Standard username/password | `DaoAuthenticationProvider` + `ProviderManager` | `UserDetailsRepositoryReactiveAuthenticationManager` + `ReactiveUserDetailsService` | Reuse `PasswordEncoder` and `UserDetails`, replace provider/manager accordingly |
| Storing auth during processing | `SecurityContextHolder` typically backed by ThreadLocal | `ReactiveSecurityContextHolder` backed by Reactor Context | Do not rely on Servlet ThreadLocal inside reactive chains |
| HTTP configuration | `HttpSecurity`, `SecurityFilterChain` | `ServerHttpSecurity`, `SecurityWebFilterChain` | WebFlux uses a `WebFilter` chain, not Servlet `Filter`s |
| In-memory user store | `InMemoryUserDetailsManager` | `MapReactiveUserDetailsService` | Convenient for demos/tests; production data usually goes through a repository adapter |
| Pipeline verification | Expect synchronous return value or exception | `StepVerifier` subscribes and verifies `onNext/onError/onComplete` | Reactive errors are not necessarily thrown synchronously when invoking the method |

**Distinguishing lookup from authentication:** `ReactiveUserDetailsService` only loads user information and authorities. It **does not replace** password checks, account status checks, or creating an authenticated token. `UserDetailsRepositoryReactiveAuthenticationManager` is the standard component that validates username/password using a `ReactiveUserDetailsService` and a `PasswordEncoder`. If legacy logic included MFA, tenant checks, password expiration, or a custom provider chain, you must deliberately migrate those rules as well.

### 1.1. The Three Outcomes of `ReactiveAuthenticationManager`

The `Mono<Authentication> authenticate(Authentication request)` contract distinguishes:

- **`onNext(authenticatedAuthentication)` followed by `onComplete`:** credentials are valid; the result has `isAuthenticated() == true` and the appropriate principal/authorities.
- **`onError(AuthenticationException)`:** the manager recognizes the authentication request, but authentication fails—for example due to a wrong password or a locked account. Do not convert this into `Mono.empty()`, because doing so loses the "invalid credentials" signal.
- **`onComplete` without emitting a value (`Mono.empty()`):** the manager **cannot decide** on that authentication request—for example, a manager that only supports another token type. When multiple managers are composed, the dispatcher can then try the next manager. Never use `Mono.empty()` to "silently fail login".

Note: `ReactiveUserDetailsService` has its own contract. A missing user is typically represented by `Mono.empty()`; the standard manager converts that into an authentication failure. Never write code that grants access when lookup completes empty.

## 2. Why Changing the Return Type Alone Is Not Enough

Legacy synchronous example:

~~~java
UserDetails user = legacyUserDetailsService.loadUserByUsername(username);
return user;
~~~

A flawed "migration" often looks like this:

~~~java
@Override
public Mono<UserDetails> findByUsername(String username) {
    // WRONG: synchronous JDBC/LDAP already ran BEFORE Mono was created.
    return Mono.just(
        legacyUserDetailsService.loadUserByUsername(username));
}
~~~

`Mono.just(...)` evaluates its argument **eagerly**. If `loadUserByUsername` hits JDBC/JPA, LDAP, or a synchronous HTTP client, the call can block the Reactor Netty thread handling the request. Switching to `Mono.justOrEmpty(...)` does not fix the issue either.

The next snippet introduces **lazy execution** but is still incomplete:

~~~java
return Mono.fromCallable(
    () -> legacyUserDetailsService.loadUserByUsername(username));
~~~

It defers execution until subscription, yet if the subscriber runs on the event loop, the blocking operation still executes **on the event loop**. When legacy APIs cannot yet be removed, you need **both** `Mono.fromCallable` and `subscribeOn(Schedulers.boundedElastic())`. Once R2DBC/reactive drivers or a reactive HTTP client are available, prefer true non-blocking APIs over relying on `boundedElastic` long-term.

Another mistake is calling `Mono.block()` inside a custom `ReactiveAuthenticationManager` to "fetch the user easily":

~~~java
// WRONG on an event loop; also defeats the benefits of the pipeline.
UserDetails user = reactiveUsers.findByUsername(username).block();
~~~

In WebFlux, **compose publishers with `flatMap`/`map`**. Calling `block()` on a non-blocking thread can immediately throw `IllegalStateException` in Reactor. That is distinct from a bad-credentials failure.

## 3. Approach A — Implementing a Pure ReactiveUserDetailsService

Suppose the database has an accounts table with username, password hash, enabled flag, and authorities. Once the repository already uses R2DBC or a genuine reactive client, build a user-lookup adapter like the following. This is a **repository-integration illustration**, not a standalone program because `AccountRepository`/`Account` are application domain models:

~~~java
public interface AccountRepository {
    Mono<Account> findByUsername(String username);
}

public record Account(
    String username,
    String passwordHash,
    boolean enabled,
    String role
) {}

public final class DatabaseReactiveUsers
        implements ReactiveUserDetailsService {

    private final AccountRepository accounts;

    public DatabaseReactiveUsers(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    public Mono<UserDetails> findByUsername(String username) {
        return accounts.findByUsername(username)
            .map(account -> User.withUsername(account.username())
                .password(account.passwordHash()) // stored hash!
                .disabled(!account.enabled())
                .roles(account.role())             // e.g., "USER"
                .build());
    }
}
~~~

Required imports: `reactor.core.publisher.Mono`; `org.springframework.security.core.userdetails.User`, `UserDetails`, and `ReactiveUserDetailsService`. A real application must map **all** applicable flags (locked, account expired, credentials expired) along with authorities; do not omit locked-account checks just because a demo only shows `enabled`. If stored roles already carry the `ROLE_USER` authority prefix or permission strings like `document:write`, map them accurately with `authorities(...)` and avoid accidentally double-prefixing `ROLE_` via `roles(...)`.

With a reactive repository, `findByUsername` returns `Mono.empty()` when the username is not found. If the database fails, let the error propagate via `onError` and classify it as an **infrastructure error**—do not add a blanket `onErrorResume(error -> Mono.empty())`, which would turn database outages into "user not found" and mask incidents.

**What to preserve during migration:** password values read from the column must be **hashes**, not plaintext; hash algorithms and prefixes like `{bcrypt}` must remain compatible with `PasswordEncoder`. Never re-encode an already-hashed password on every read. Changing hashing algorithms or rehashing passwords must happen through a controlled data migration, never silently inside `findByUsername`.

## 4. Approach B — A Runnable WebFlux Username/Password Configuration

This section uses an in-memory user to focus on contracts and bean wiring. The file **`src/main/java/demo/migration/ReactiveMigrationApplication.java`** below is a complete Spring Boot WebFlux application with a public endpoint and an authenticated endpoint:

~~~java
package demo.migration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
public class ReactiveMigrationApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveMigrationApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class ReactiveSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService reactiveUsers(PasswordEncoder encoder) {
        // DEMO credentials only; never hard-code production secrets.
        UserDetails user = User.withUsername("alice")
            .password(encoder.encode("changeit"))
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(user);
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
            ReactiveAuthenticationManager manager) {

        return http
            .authenticationManager(manager)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public/**").permitAll()
                .anyExchange().authenticated())
            .httpBasic(withDefaults())
            .build();
    }
}

@RestController
class ExampleRoutes {

    @GetMapping("/public/ping")
    Mono<String> publicPing() {
        return Mono.just("pong");
    }

    @GetMapping("/private/me")
    Mono<String> currentUser() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName());
    }
}
~~~

Required dependencies configuration in a Spring Boot Gradle project (using the existing Boot BOM/plugin for version management):

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

Run the application:

~~~bash
./gradlew bootRun
~~~

Test with curl (replace `localhost:8080` if the application uses a different port):

~~~bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/private/me
curl -i -u alice:changeit http://localhost:8080/private/me
curl -i -u alice:wrong http://localhost:8080/private/me
~~~

Expected HTTP outcomes for this demo configuration:

| Request | Expected outcome | Why |
| --- | --- | --- |
| `GET /public/ping`, no credentials | **200**, body `pong` | URL matches `permitAll()` |
| `GET /private/me`, no credentials | **401** | `anyExchange().authenticated()` and HTTP Basic challenge |
| `GET /private/me`, `alice:changeit` | **200**, body `alice` | Manager verifies hash and emits valid authentication |
| `GET /private/me`, `alice:wrong` | **401** | Wrong password, authentication fails |

Headers, log ordering, and Gradle output messages depend on versions and configuration; the table describes the semantic behaviors to verify. The demo password is hashed with `PasswordEncoder` at application startup and verified by the manager. Do not use `User.withDefaultPasswordEncoder()` or `{noop}` for real data.

**Who does what in this example?**

1. `ReactiveUserDetailsService` supplies `alice`'s `UserDetails`.
2. `UserDetailsRepositoryReactiveAuthenticationManager` loads the user, verifies credentials/status, and returns `Mono<Authentication>`.
3. `ServerHttpSecurity.authenticationManager(manager)` connects the manager to WebFlux authentication.
4. `httpBasic(...)` extracts the Basic header and handles challenges/errors in the security WebFilter chain.
5. `ReactiveSecurityContextHolder.getContext()` reads authentication from the **Reactor Context** during the request; do not read `SecurityContextHolder.getContext()` and assume ThreadLocal will remain accurate across scheduler switches.

**Do not mix the two stacks:** a Servlet `SecurityFilterChain(HttpSecurity)` does not replace `SecurityWebFilterChain(ServerHttpSecurity)`. If a project contains both the web MVC and webflux starters, Spring Boot may choose the Servlet application type; verify the actual web application type and dependencies before concluding the WebFlux configuration is active.

## 5. Approach C — Temporarily Bridging a Synchronous UserDetailsService

If you currently depend on a synchronous JDBC/JPA/LDAP repository and cannot migrate it immediately, you can wrap the legacy `UserDetailsService` with a `ReactiveUserDetailsService`. Create **`src/main/java/demo/migration/LegacyUserDetailsBridge.java`** (this is a complete class; the legacy backend is supplied by the application):

~~~java
package demo.migration;

import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public final class LegacyUserDetailsBridge
        implements ReactiveUserDetailsService {

    private final UserDetailsService legacy;

    public LegacyUserDetailsBridge(UserDetailsService legacy) {
        this.legacy = legacy;
    }

    @Override
    public Mono<UserDetails> findByUsername(String username) {
        return Mono.fromCallable(
                () -> legacy.loadUserByUsername(username))
            .subscribeOn(Schedulers.boundedElastic())
            .onErrorResume(
                UsernameNotFoundException.class,
                error -> Mono.empty());
    }
}
~~~

Registering it in the Spring context when a `UserDetailsService` bean **already exists** and you want to use `UserDetailsRepositoryReactiveAuthenticationManager`:

~~~java
@Bean
ReactiveUserDetailsService reactiveUsers(UserDetailsService legacy) {
    return new LegacyUserDetailsBridge(legacy);
}
~~~

The `@Bean` snippet above is an **integration piece inside an `@Configuration` class**, not a standalone file. When adding it to the application, replace the in-memory `reactiveUsers(...)` bean from Section 4 with this adapter bean to avoid **multiple beans of the same type causing ambiguity**; keep the rest of the configuration if using username/password authentication.

**Why is this bridge valid with respect to threading?**

- `Mono.fromCallable` defers the query until subscription.
- `subscribeOn(Schedulers.boundedElastic())` moves the synchronous source onto a scheduler suited for blocking calls, keeping the request-serving event loop unblocked.
- `UsernameNotFoundException` specifically is mapped to an empty publisher, matching the "user absent" contract of reactive lookup. **DB connection failures, timeouts, and mapping errors** are not swallowed; they remain `onError` signals to be handled as service errors.
- `UserDetails` preserves password hashes, authorities, and account status from the legacy system; the reactive manager still performs authentication.

**Important limitations:** the bridge does not make JDBC/JPA/LDAP non-blocking. Bounded elastic has finite workers and queue capacity; you must check connection pools, driver timeouts, concurrency, and p95/p99 under real load. `Mono.timeout(...)` does not guarantee interrupting an already-started synchronous JDBC query. If the legacy backend relies on lazy JPA associations, also evaluate transaction and session boundaries when switching worker threads.

Avoid patterns like these:

~~~java
// WRONG: fromCallable is lazy but can still run directly on the event loop.
return Mono.fromCallable(() -> legacy.loadUserByUsername(username));

// WRONG: work executes before subscribeOn takes effect.
return Mono.just(legacy.loadUserByUsername(username))
    .subscribeOn(Schedulers.boundedElastic());
~~~

## 6. Approach D — Bridging a Monolithic Legacy AuthenticationManager

When the legacy system has a **custom `AuthenticationManager`** with an `AuthenticationProvider` chain, LDAP bind, or bespoke rules that are hard to split apart right away, Spring Security provides **`ReactiveAuthenticationManagerAdapter`**. Integration example (assuming a legacy `AuthenticationManager` bean exists):

~~~java
@Bean
ReactiveAuthenticationManager reactiveManager(
        AuthenticationManager legacyManager) {

    ReactiveAuthenticationManagerAdapter adapter =
        new ReactiveAuthenticationManagerAdapter(legacyManager);
    adapter.setScheduler(Schedulers.boundedElastic());
    return adapter;
}
~~~

Corresponding imports: `org.springframework.security.authentication.AuthenticationManager`, `ReactiveAuthenticationManager`, `ReactiveAuthenticationManagerAdapter`, `reactor.core.scheduler.Schedulers`, and `org.springframework.context.annotation.Bean`.

The adapter wraps synchronous manager calls behind the reactive interface; configure an appropriate scheduler whenever the legacy implementation **may block**. It lets you keep working providers running during migration, though it incurs thread overhead and continues depending on legacy architecture. Prefer migrating individual providers/lookups to reactive once genuine non-blocking APIs exist.

**Choose one execution path per authentication mechanism:**

- If only `UserDetailsService` remains synchronous, use the **lookup bridge** in Section 5 together with `UserDetailsRepositoryReactiveAuthenticationManager` so the reactive manager verifies passwords.
- If you must preserve **an entire synchronous `AuthenticationManager`**, use `ReactiveAuthenticationManagerAdapter` from Section 6; do not build a parallel new manager for the same credential flow without an explicit dispatch design.
- Once a reactive user store is available, use the direct manager from Section 4. This is the normal target state.

Do not turn an adapter into a "new login mechanism": **never accept mismatched token types**, skip password checks, bypass account status, or swallow exceptions. Legacy rules such as rate limiting, account lockout, auditing, tenant scoping, or MFA must all be tested under WebFlux.

## 7. Implementing ReactiveAuthenticationManager Directly for Custom Tokens/Flows

You can implement `ReactiveAuthenticationManager` directly to handle a custom credential type, but you must preserve the three states: **success / cannot determine / failure**. Conceptual pattern:

~~~java
@Override
public Mono<Authentication> authenticate(Authentication request) {
    if (!(request instanceof MyApiKeyAuthenticationToken token)) {
        return Mono.empty(); // This manager does not support this token type.
    }

    return apiKeys.findByKey(token.getKey()) // Reactive query API.
        .switchIfEmpty(Mono.error(
            new BadCredentialsException("Invalid credentials")))
        .map(account -> new UsernamePasswordAuthenticationToken(
            account.principal(), null, account.authorities()));
}
~~~

`MyApiKeyAuthenticationToken` and `apiKeys` are **hypothetical application types and dependencies**, so this snippet is **structural illustration code** and does not compile standalone. Real API-key authentication also requires constant-time/safe secret comparison, expiration, revocation, permission scoping, and an appropriate `ServerAuthenticationConverter` to extract the token from the request. Do not use the standard password manager to validate Bearer JWTs; Spring Security Resource Server already provides dedicated authentication/filters for JWT and opaque tokens.

In the custom branch, when a recognized token type is not found, return `Mono.error(BadCredentialsException)`. `Mono.empty()` means "I cannot decide", not "reject". Return an `Authentication` marked authenticated with verified authorities—never copy `isAuthenticated=true` from an unverified request. Perform I/O with a reactive client or offload legacy calls onto `boundedElastic`.

## 8. Testing the Reactive Contract with JUnit and StepVerifier

Create **`src/test/java/demo/migration/ReactiveAuthenticationContractTest.java`**. This is a **complete test class** that requires neither an HTTP server nor a database; `spring-security-test` and `reactor-test` were declared in Section 4:

~~~java
package demo.migration;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReactiveAuthenticationContractTest {

    private final PasswordEncoder encoder =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();

    private final ReactiveUserDetailsService users =
        new MapReactiveUserDetailsService(
            User.withUsername("alice")
                .password(encoder.encode("changeit"))
                .roles("USER")
                .build()
        );

    private final ReactiveAuthenticationManager manager =
        createManager();

    private ReactiveAuthenticationManager createManager() {
        UserDetailsRepositoryReactiveAuthenticationManager result =
            new UserDetailsRepositoryReactiveAuthenticationManager(users);
        result.setPasswordEncoder(encoder);
        return result;
    }

    private Authentication request(String user, String password) {
        return UsernamePasswordAuthenticationToken.unauthenticated(
            user, password);
    }

    @Test
    void findsExistingUser() {
        StepVerifier.create(users.findByUsername("alice"))
            .assertNext(found -> {
                assertEquals("alice", found.getUsername());
                assertTrue(encoder.matches(
                    "changeit", found.getPassword()));
            })
            .verifyComplete();
    }

    @Test
    void unknownUserLookupIsEmpty() {
        StepVerifier.create(users.findByUsername("unknown"))
            .verifyComplete();
    }

    @Test
    void acceptsCorrectCredentialsAndExposesAuthorities() {
        StepVerifier.create(
                manager.authenticate(request("alice", "changeit")))
            .assertNext(auth -> {
                assertTrue(auth.isAuthenticated());
                assertEquals("alice", auth.getName());
                assertTrue(auth.getAuthorities().stream()
                    .anyMatch(a -> a.getAuthority()
                        .equals("ROLE_USER")));
            })
            .verifyComplete();
    }

    @Test
    void wrongPasswordFailsAsAuthenticationError() {
        StepVerifier.create(
                manager.authenticate(request("alice", "wrong")))
            .expectError(BadCredentialsException.class)
            .verify();
    }

    @Test
    void unknownUserCannotAuthenticate() {
        StepVerifier.create(
                manager.authenticate(request("unknown", "anything")))
            .expectError(AuthenticationException.class)
            .verify();
    }
}
~~~

Run a single test class from the project root with the Gradle wrapper:

~~~bash
./gradlew test --tests demo.migration.ReactiveAuthenticationContractTest
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests demo.migration.ReactiveAuthenticationContractTest
~~~

**Expectation:** five tests PASS in an environment with compatible dependencies. Do not rely on specific Gradle stdout wording. `StepVerifier` actually subscribes and verifies signals; merely calling `manager.authenticate(...)` followed by `assertNotNull(...)` is insufficient. The tests above also separate **missing user lookup = empty** from **missing user authentication = error**. The exact exception subclass from a manager can vary by implementation/configuration, so the missing-user test asserts `AuthenticationException` generally, whereas the wrong-password test asserts `BadCredentialsException`.

### 8.1. Adding Tests for the Legacy Adapter

For the bridge in Section 5, you need a mock/stub dependency to verify exception translation and scheduler behavior. The snippet below is an **addition to an appropriate test class**, not a standalone runnable class:

~~~java
UserDetailsService legacy = username -> {
    if (!"alice".equals(username)) {
        throw new UsernameNotFoundException(username);
    }
    return User.withUsername("alice")
        .password("{noop}demo-only")
        .roles("USER")
        .build();
};

LegacyUserDetailsBridge bridge = new LegacyUserDetailsBridge(legacy);

StepVerifier.create(bridge.findByUsername("alice"))
    .assertNext(user -> assertEquals("alice", user.getUsername()))
    .verifyComplete();

StepVerifier.create(bridge.findByUsername("missing"))
    .verifyComplete();
~~~

Additional imports: `org.springframework.security.core.userdetails.UserDetailsService` and `UsernameNotFoundException`. The `{noop}` hash in this fixture only illustrates a `UserDetails` instance and **must not be used for real passwords**. To test end-to-end authentication, use `PasswordEncoder` as in the full test example and cover both valid and invalid passwords.

### 8.2. Checking HTTP Behavior After Manager Tests Pass

Direct method tests do not prove the security filter chain is wired properly. Run the application from Section 4 and use curl or `WebTestClient` with a real Spring context to verify:

- `/public/ping` requires no auth.
- `/private/me` without credentials is rejected.
- `/private/me` with valid credentials succeeds and reads the exact username from Reactor Context.
- Wrong passwords or disabled/locked accounts cannot produce a valid authentication.
- When using a bridge, requests go through the real repository/manager; do not mock away the entire manager in tests aimed at detecting blocking.

Distinguish **method-level errors** (`AuthenticationException` in Reactor signals) from **HTTP status codes** (such as 401 for invalid Basic credentials). WebFlux security filters translate errors into HTTP responses via the authentication entry point and exception handling; direct manager tests should not assert an HTTP status code.

## 9. Security Context Across Thread Switches

In Servlet code, legacy implementations frequently call:

~~~java
Authentication current =
    SecurityContextHolder.getContext().getAuthentication();
~~~

`SecurityContextHolder` defaults to ThreadLocal. In WebFlux, requests and callbacks can execute across multiple schedulers; do not copy this logic verbatim into a custom reactive authentication/authorization service to read the principal.

Inside a reactive pipeline, access it with:

~~~java
Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());
}
~~~

Required imports: `org.springframework.security.core.context.ReactiveSecurityContextHolder`, `reactor.core.publisher.Mono`. The snippet above is an **illustrative method** inside a bean or controller, not a standalone Java file. When the HTTP filter chain authenticates successfully, it populates the context in the corresponding reactive chain.

When switching onto `Schedulers.boundedElastic()` using Reactor operators, Reactor Context propagates with the subscription; however, manually calling `subscribe()` inside a service or spawning `new Thread(...)` can detach lifecycle and security context. Never store tokens or passwords in static fields or ThreadLocals as a "fix" for lost context. If context is needed inside a synchronous adapter, pass the **specific authenticated value** as a parameter or design a context-aware reactive flow instead of assuming Servlet `SecurityContextHolder` reflects the right user.

## 10. Step-by-Step Safe Migration Checklist

**Step 1 — Inventory actual contracts in use.** Identify `UserDetailsService` sources, `AuthenticationManager`, `AuthenticationProvider` beans, `PasswordEncoder`, account-state checks, tenant/multi-factor rules, and HTTP mechanisms (form, basic, bearer, etc.). Change only the components genuinely involved in the request flow being migrated.

**Step 2 — Verify the WebFlux runtime.** Inspect dependencies, confirm the app boots with the reactive web application type, verify endpoints run on Reactor Netty/WebFlux, and ensure security uses `SecurityWebFilterChain`/`ServerHttpSecurity`. Do not swap a Servlet bean and assume the reactive chain automatically sees it.

**Step 3 — Choose the data path.** When reactive drivers are supported, use `ReactiveUserDetailsService` backed by a reactive repository; otherwise use the `fromCallable + boundedElastic` bridge for lookup, or `ReactiveAuthenticationManagerAdapter` for a monolithic legacy manager. Document a plan to retire the bridge and bound concurrency.

**Step 4 — Preserve security semantics.** Keep algorithm/password-hash compatibility, authorities, disabled/locked/expired checks, error policies, auditing, and tenant scoping. Never log plaintext credentials and never grant a default role when lookup fails.

**Step 5 — Configure one clear authentication path.** Create the appropriate manager, inject it into `ServerHttpSecurity.authenticationManager(...)`, and configure `httpBasic`/`formLogin`/custom filters as required. Avoid competing `ReactiveUserDetailsService` beans unless explicit qualifiers or dispatch logic are designed.

**Step 6 — Test contracts first, HTTP second.** With `StepVerifier`, verify user found/missing, right/wrong password, disabled accounts, and storage errors. With `WebTestClient` or curl, verify public/private routes, success/failure responses, HTTP status, and Reactor Context. To check for blocking, use tools like BlockHound and realistic load tests.

**Step 7 — Monitor during rollout.** Compare authentication success/failure rates, 401 causes, login p95/p99, CPU spent on password hashing, `boundedElastic` queue/threads, connection pools, timeouts/exceptions, and saturation under load. Set actionable alerts; never log passwords or tokens.

## 11. Common Debugging Scenarios

| Symptom | Likely cause to check | Resolution |
| --- | --- | --- |
| `ReactiveUserDetailsService` exists, but login still fails | Manager not wired into WebFlux chain, or app is running as Servlet | Check web application type, `SecurityWebFilterChain`, `ServerHttpSecurity`, and the injected manager |
| `Mono.just(legacy.load...)` causes slow/blocking requests | Synchronous call executed before publisher creation | Use `fromCallable(...).subscribeOn(boundedElastic)` or switch backend to a reactive driver |
| Wrong password causes manager to return `Mono.empty()` | Custom manager confuses "failed" with "unsupported" | Return `Mono.error(BadCredentialsException)` for recognized credentials that are invalid |
| Missing user exposes system errors or inconsistent messages | Mixing legacy `UsernameNotFoundException` contract with empty publisher | Map only **not found** to empty in user lookup; let the manager emit authentication failure and preserve anti-enumeration policy |
| `PasswordEncoder` reports invalid format | Legacy password hashes lack prefixes or encoder changed | Verify stored hash formats and compatible encoder; migrate hashes deliberately, never use `NoOp` in production |
| `ROLE_USER` fails to match `hasRole('USER')` | Role/authority stored with wrong prefix or duplicated `ROLE_` | Use `roles("USER")` for bare role names, or `authorities("ROLE_USER")` for already-prefixed authorities |
| Login succeeds, but principal disappears after `publishOn/flatMap` | Relied on ThreadLocal or manual `subscribe()` detached context | Use Reactor Context and `ReactiveSecurityContextHolder`; keep operators chained in one sequence |
| Auth failure returns 500 instead of 401 | Storage error caught/converted wrongly, or exception translation bypassed security filter | Inspect stack traces, classify `AuthenticationException`, and test HTTP handler/filter |
| User data exists, yet disabled account still gets in | Account-state flags omitted when mapping `UserDetails` or custom manager skipped checks | Map all account flags and test disabled/locked/expired states |
| Bounded elastic saturated, high p99 | Too many blocking backend calls or long driver timeouts | Bound concurrency/connection pools, set driver timeouts, and incrementally adopt non-blocking drivers |
| Tests pass, but production runs different logic | Tests mocked out manager/service or bean ambiguity occurred | Integration-test real beans, verify wiring, and test both denied and success cases |
| Multiple token types (Basic/JWT/API key) | Single manager handles wrong token or dispatch order is wrong | Scope filters/managers by authentication mechanism; use reactive manager resolvers/delegation only when genuinely needed |

### Subtle Traps

- **Do not create `Mono<Mono<UserDetails>>`** by calling `map` on an operation that already returns a publisher; use `flatMap` to flatten the chain.
- **Do not write `onErrorResume(error -> Mono.empty())`** in an authentication pipeline: it can hide database outages or turn bad credentials into an "undecidable" case.
- **Do not call `subscribe()` inside `authenticate`** and return a separate publisher; this detaches the request from the auth flow and breaks error propagation, cancellation, and context.
- **Do not run all password hashing directly on the event loop.** `UserDetailsRepositoryReactiveAuthenticationManager` uses a dedicated internal scheduler suited for CPU-intensive hash verification; in custom adapters, account explicitly for CPU cost and actual blocking instead of assuming default schedulers cover everything.
- **Do not migrate `DaoAuthenticationProvider` as a reactive bean by name alone.** It is a synchronous Servlet provider; the native reactive choice is `UserDetailsRepositoryReactiveAuthenticationManager`, or a deliberate legacy manager bridge.
- **Do not use `@EnableReactiveMethodSecurity` in place of `@EnableWebFluxSecurity`.** Method security and web authentication are separate layers; enabling method security alone does not wire HTTP Basic login filters.
- **Do not treat `Mono.empty()` from lookup as "anonymous authenticated".** A nonexistent user grants no privileges; systems must preserve deny-by-default when unauthenticated.
- **Do not expect unit tests on a manager alone to guarantee HTTP 401/403.** HTTP status responses belong to WebFlux security filters and must be verified at that layer.

## 12. Self-Assessment

Answer the following questions by referencing the examples and adapting tests for each scenario:

1. In the legacy `UserDetailsService`, a missing user throws an exception; in the new `ReactiveUserDetailsService`, what signal should be emitted? Why must the manager still convert that signal into an authentication failure?
2. When is `ReactiveAuthenticationManager.authenticate` allowed to emit `Mono.empty()`, and when must it emit `Mono.error(BadCredentialsException)`?
3. Why can both `Mono.just(legacyStore.find(username))` and `Mono.fromCallable(...)` without a scheduler block the event loop?
4. When a database lacks a reactive driver, in what situation do you choose `LegacyUserDetailsBridge` versus `ReactiveAuthenticationManagerAdapter`? What performance risks apply?
5. When the password is correct but the role is wrong, is this an **authentication** failure or an **authorization** failure? How do the tests differ?
6. Why can a Servlet `AuthenticationManager` bean not be used directly by `SecurityWebFilterChain`?
7. When execution hops onto `boundedElastic`, where should current authentication information be read from inside a reactive pipeline?
8. How would you test account locked/disabled states and DB connection errors so that infrastructure failures never turn into "user not found"?

The exercise is complete when you have **reactive contract tests** verifying success and failure, **WebFlux tests** verifying protected routes/HTTP behavior, and **evidence of non-blocking event-loop execution** for the account lookup path. If a temporary bridge is used, explicitly document the remaining blocking dependency and migration plan.

## Official Documentation

- Spring Security WebFlux Security: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- `ReactiveUserDetailsService` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/ReactiveUserDetailsService.html
- `ReactiveAuthenticationManager` API and three outcome states: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html
- `UserDetailsRepositoryReactiveAuthenticationManager` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/UserDetailsRepositoryReactiveAuthenticationManager.html
- `ReactiveAuthenticationManagerAdapter` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ReactiveAuthenticationManagerAdapter.html
- Reactor Reference – wrapping blocking calls: https://projectreactor.io/docs/core/release/reference/faq.html
- Spring Security Reactive testing: https://docs.spring.io/spring-security/reference/6.5/reactive/test/index.html
