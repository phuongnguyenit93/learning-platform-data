# Distinguishing Authentication Success, Mono.empty, and Error Signals in Spring Security Reactive

> **Topic:** Spring Security - authentication → **Reactive authentication**. Illustrative environment: **Spring Boot 3.x, Spring Security 6.x, Spring WebFlux, Reactor, Java 17+**. The focus is the `ReactiveAuthenticationManager.authenticate(Authentication)` contract: there are **three distinct signal types**, each carrying a specific security meaning. This article also distinguishes **ServerAuthenticationConverter** signals from **ReactiveAuthenticationManager** signals, explains error handling in `AuthenticationWebFilter`, and tests them with `StepVerifier` and `WebTestClient`.

## 1. ReactiveAuthenticationManager Does Not Return a Boolean

In a traditional Servlet application, `AuthenticationManager.authenticate(...)` normally returns an `Authentication` or throws `AuthenticationException`. In WebFlux, the corresponding interface is:

```java
package org.springframework.security.authentication;

import org.springframework.security.core.Authentication;
import reactor.core.publisher.Mono;

@FunctionalInterface
public interface ReactiveAuthenticationManager {
    Mono<Authentication> authenticate(Authentication authentication);
}
```

This is a **condensed signature** for illustration; the actual interface source belongs to Spring Security. `Mono<Authentication>` is not an already-resolved authentication value; it is a **Publisher** that can emit **0 or 1 item** and then complete, or emit **an error signal**. Reactor does not allow `null` as an `onNext` element.

Under the official API contract, there are **three outcomes**:

| Outcome at the ReactiveAuthenticationManager level | Reactive Streams signal | Authentication semantics |
| --- | --- | --- |
| `Mono.just(verifiedAuthentication)` | `onNext(Authentication)` → `onComplete` | **Authentication succeeded**; the resulting token must hold verified principal/authorities |
| `Mono.empty()` | `onComplete`, **no onNext** | The manager **cannot make a decision** for this request, e.g., unsupported token type; **not** “wrong password” |
| `Mono.error(new BadCredentialsException(...))` | `onError(AuthenticationException)` | **Processed, but authentication failed**; must follow the error/failure handler path |

A few very short code examples:

```java
Mono<Authentication> success =
    Mono.just(UsernamePasswordAuthenticationToken.authenticated(
        verifiedPrincipal, null, verifiedAuthorities));

Mono<Authentication> noDecision = Mono.empty();

Mono<Authentication> badCredentials =
    Mono.error(new BadCredentialsException("Invalid credentials"));
```

Here `verifiedPrincipal` and `verifiedAuthorities` must be obtained **after** verifying the credentials and identity data from a trusted source. The three variables above illustrate the signals, **not** three interchangeable branches for the same error.

### Key Principles to Remember

- **Item emitted**: the manager produced an Authentication result. For success, it must be a verified authentication, typically `isAuthenticated() == true`.
- **Empty completion**: the manager produced no authentication result; it abstains from **deciding**, asserting neither that credentials are valid nor invalid.
- **Error emitted**: the manager asserts a failure. For wrong password, use `BadCredentialsException` or an appropriate `AuthenticationException`; for infrastructure outages, preserve the distinction between system errors and invalid credentials.

Do not write `return null;` instead of `Mono.empty()`, do not write `Mono.just(null)` (Reactor forbids null items), and do not use `Mono.just(unauthenticatedToken)` as a way to report a “partial” successful login.

## 2. Two Layers of Mono.empty That Are Easily Confused

Spring Security WebFlux typically involves `AuthenticationWebFilter` and `ReactiveAuthenticationManager`, yet **two different publishers** participate in the processing flow:

1. **`ServerAuthenticationConverter.convert(ServerWebExchange)`** converts an HTTP request into an **unverified** `Authentication`.
2. **`ReactiveAuthenticationManager.authenticate(Authentication)`** receives the request token and proves or rejects the identity.

HTTP Basic example:

```text
GET /private
Authorization: Basic <base64(username:password)>
        |
        v
AuthenticationWebFilter
        |
        +-- requiresAuthenticationMatcher(request)?
        |       false -> continue chain, no attempt
        |
        v
ServerAuthenticationConverter
        |
        +-- Mono.empty()
        |       -> NO convertible credentials;
        |          skip attempt, continue chain
        |
        '-- Mono<Authentication> (request token)
                |
                v
        ReactiveAuthenticationManager.authenticate(...)
                |
                +-- onNext(authenticated token) -> success handler
                |
                +-- onComplete without value -> no decision;
                |    may be evaluated by another manager when delegating
                |
                '-- onError(AuthenticationException)
                     -> failure handler / authentication entry point
```

**Crucial distinction:** `Mono.empty()` from the **converter** means “this request does not provide an authentication request recognized by the converter,” so the filter has no attempt to send to the manager. `Mono.empty()` from the **manager** means “this manager could not determine an outcome for the converted authentication.” Final details of how a filter/manager chain behaves when a manager returns empty depend on configuration and implementation; you cannot assume HTTP `401`, `403`, or success from a standalone `Mono.empty()`.

Examples:

- GET `/private` without `Authorization`: the Basic converter produces no token; authorization on the protected endpoint requires authentication, and the HTTP Basic entry point typically returns `401 Unauthorized`.
- GET `/private` with `Authorization: Basic ...` of the right type but wrong password: the manager **must emit an error** `BadCredentialsException`; the filter failure handler processes it, typically returning `401`.
- A manager supporting only API keys receives a username/password token: the manager may return `Mono.empty()` so another manager can attempt that token type.
- If a request has a token of a supported type but no account is found: do **not** turn it into empty at the authentication boundary; this is a credential failure requiring an error signal.

## 3. How to Read a Reactor Chain

A `Mono` has one of three shapes:

```text
SUCCESS:
Subscription
  |-- onNext(Authentication { authenticated=true })
  '-- onComplete

EMPTY:
Subscription
  '-- onComplete

ERROR:
Subscription
  '-- onError(BadCredentialsException)
```

**Empty is not an error.** Therefore:

| Reactor operator | Success | Empty | Error |
| --- | --- | --- | --- |
| `map(mapper)` | Transforms Authentication | Skips mapper, remains empty | Propagates error |
| `flatMap(mapper)` | Invokes mapper | Skips mapper, remains empty | Propagates error |
| `switchIfEmpty(fallback)` | Does not use fallback | Uses fallback publisher | **Does not catch errors** |
| `onErrorResume(type, fallback)` | Does not call fallback | Does not call fallback | Handles matching error only |
| `defaultIfEmpty(value)` | Keeps original item | Replaces empty with provided item | Does not catch errors |
| `doOnNext(...)` | Runs with Authentication | Does not run | Does not run |
| `doOnError(...)` | Does not run | Does not run | Runs with Throwable |
| `doOnSuccess(value)` | Called with Authentication | Called with **null** on empty completion | Does not run |
| `doOnTerminate(...)` | Called on termination | Called on termination | Called on termination |
| `doFinally(...)` | Called on finish | Called on finish | Called on finish or cancel |

`doOnSuccess(null)` does **not** mean the Mono emitted a null element: it is the special callback argument signaling empty completion. Never write `if (value == null) loggedIn = true;` or use this callback to “confirm Authentication”.

Another observation: `doOnNext(...)` runs only when an `Authentication` is actually emitted. If “log success” code is placed in `doOnSuccess` without checking the value, it can falsely log success for `Mono.empty()`.

### Operator Anti-Patterns

**Wrong — turning every password error into “no decision”:**

```java
return verifyCredentials(token)
    .onErrorResume(BadCredentialsException.class, error -> Mono.empty());
```

If multiple managers are used, another manager might be tried next; converting an error into empty loses the “tried and failed” semantics. Do not use a fallback branch to dodge failures.

**Wrong — turning “unsupported token” into wrong password:**

```java
if (!(token instanceof UsernamePasswordAuthenticationToken)) {
    return Mono.error(new BadCredentialsException("wrong password"));
}
```

A username/password provider must not claim wrong password for an API key/JWT token it cannot verify. Return `Mono.empty()` for **unsupported** token contracts.

**Wrong — turning an unchecked authentication into a success result:**

```java
return Mono.just(token); // client token is still unauthenticated
```

Filters and authorization would receive an object that cannot be treated as a verified identity. Return an authenticated token only after verifying credentials, account state, and server-sourced authorities.

**Right — separating each case:**

```java
if (!supports(token)) {
    return Mono.empty(); // Does not handle this token type.
}
return verifySupportedToken(token)
    .switchIfEmpty(Mono.error(
        new BadCredentialsException("Invalid credentials")));
```

The code above is a **conceptual pattern**: `verifySupportedToken` is an application-defined method; the idea is that if a reactive account store returns empty because **no matching user exists**, the username/password manager boundary must translate that into an authentication error rather than letting empty escape as if the provider abstained.

## 4. Standalone Java 17+ Example in a Spring WebFlux Application

The example uses HTTP Basic on a **GET-only** API to make signals easy to observe. A custom manager accepts `UsernamePasswordAuthenticationToken`, verifies demo username/password credentials, and emits the result in a `Mono`. It creates no session; every request must resend Basic credentials. In production, prefer TLS, appropriate credential mechanisms, and rate limiting; Basic is not a safe default for all APIs or browsers.

### 4.1. Gradle Dependencies

In a Spring Boot 3.x project with the Gradle plugin and Java 17, declare:

```groovy
// build.gradle - dependencies section
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
```

Do not add `spring-boot-starter-web` (Servlet MVC) to the demo: the application needs a true reactive server. When both WebFlux and MVC starters are present, Spring Boot typically prefers the Servlet application type, which skews the tests.

### 4.2. Main Application

**`src/main/java/example/reactivesignals/ReactiveSignalsApplication.java`**

```java
package example.reactivesignals;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveSignalsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveSignalsApplication.class, args);
    }
}
```

### 4.3. Verified Principal

**`src/main/java/example/reactivesignals/VerifiedPrincipal.java`**

```java
package example.reactivesignals;

import java.security.Principal;

public record VerifiedPrincipal(
        String accountId,
        String username) implements Principal {

    @Override
    public String getName() {
        return username;
    }
}
```

`VerifiedPrincipal` contains no plaintext password or password hash, reducing exposure when the principal is read from `ReactiveSecurityContextHolder` or written to audit logs. The name and ID come from the server record after credentials have been verified. In a real product, accounts may have additional states and permissions; the provider must verify those conditions before issuing authentication.

### 4.4. ReactiveAuthenticationManager Returning All Three Signal Types

**`src/main/java/example/reactivesignals/DemoReactiveAuthenticationManager.java`**

```java
package example.reactivesignals;

import java.util.List;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.crypto.password.PasswordEncoder;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public final class DemoReactiveAuthenticationManager
        implements ReactiveAuthenticationManager {

    private final PasswordEncoder encoder;
    private final String storedPasswordHash;

    public DemoReactiveAuthenticationManager(PasswordEncoder encoder) {
        this.encoder = encoder;
        this.storedPasswordHash = encoder.encode("study-pass");
    }

    @Override
    public Mono<Authentication> authenticate(Authentication request) {

        // 1. Provider only decides username/password.
        //    Other tokens -> no decision, NOT wrong password.
        if (!(request instanceof UsernamePasswordAuthenticationToken)) {
            return Mono.empty();
        }

        // 2. Username/password in the request are untrusted.
        String username = request.getName();
        Object suppliedCredential = request.getCredentials();

        if (!(suppliedCredential instanceof String password)
                || password.isBlank()
                || username == null || username.isBlank()) {
            return Mono.error(
                new BadCredentialsException("Invalid credentials"));
        }

        // 3. fromCallable() runs only when the subscriber actually subscribes.
        //    BCrypt is CPU-intensive work; do not run on the event loop.
        return Mono.<Authentication>fromCallable(() -> {
                boolean passwordMatches =
                    encoder.matches(password, storedPasswordHash);

                // Use the same message for wrong username/wrong password.
                if (!"alice".equals(username) || !passwordMatches) {
                    throw new BadCredentialsException("Invalid credentials");
                }

                // 4. Principal and authority come from server data.
                VerifiedPrincipal principal =
                    new VerifiedPrincipal("acct-101", "alice");

                // authenticated(...) factory is called ONLY AFTER verification.
                return UsernamePasswordAuthenticationToken.authenticated(
                    principal,
                    null,
                    List.of(new SimpleGrantedAuthority("ROLE_USER")));
            })
            .subscribeOn(Schedulers.boundedElastic());
    }
}
```

**Detailed analysis:**

1. `Mono.empty()` occurs **only when** the request token is not of a type this manager is responsible for checking. This is the boundary between “unsupported/no decision” and “bad credentials”.
2. A `UsernamePasswordAuthenticationToken` request with a missing or blank username/password is a **failure**. `Mono.error(BadCredentialsException)` is the proper signal; do not return `Mono.empty()`.
3. `Mono.fromCallable(...)` creates a **cold/lazy** publisher. The password check only runs on subscription; exceptions are converted by Reactor into `onError`. Do not catch `BadCredentialsException` and return a default principal.
4. `BCryptPasswordEncoder.matches(raw, hash)` verifies the password; never compare plaintext with `equals` or rehash and compare (BCrypt uses salt). The example still performs the hash check for nonexistent usernames to reduce branching differences, though production needs comprehensive account enumeration defense, rate limiting, and timing protection.
5. `Schedulers.boundedElastic()` moves the expensive hash check off the Netty event loop. It **does not make BCrypt non-blocking I/O**. For blocking databases/JDBC, use an appropriate adapter/scheduler or reactive data sources (R2DBC); avoid calling `.block()` on the event loop.
6. The result contains only `ROLE_USER` from the server; the raw password is no longer in `getCredentials()`. `isAuthenticated()` is true because the `authenticated(...)` factory is called after verification. Never copy client-supplied `request.getAuthorities()`, headers, or claims.
7. In a production application, you must check `enabled`, `locked`, password expiry, MFA policy, tenant, and authorities from an authoritative source. The example omits these to focus on the **Mono contract**.

**A nuance about PasswordEncoder:** `encoder.encode("study-pass")` runs once when the manager bean is constructed to create the demo hash, not on every request. Real applications load stored hashes from a database/repository; if the hash is stored/read outside the event loop, use the appropriate reactive mechanism.

### 4.5. SecurityWebFilterChain for Stateless HTTP Basic

**`src/main/java/example/reactivesignals/SecurityConfig.java`**

```java
package example.reactivesignals;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    DemoReactiveAuthenticationManager demoAuthenticationManager(
            PasswordEncoder encoder) {
        return new DemoReactiveAuthenticationManager(encoder);
    }

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http,
            DemoReactiveAuthenticationManager manager) {

        NoOpServerSecurityContextRepository noOp =
            NoOpServerSecurityContextRepository.getInstance();

        http
            .securityContextRepository(noOp)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .pathMatchers("/private").authenticated()
                .pathMatchers("/admin").hasRole("ADMIN")
                .anyExchange().denyAll())
            .httpBasic(basic -> basic
                .authenticationManager(manager)
                .securityContextRepository(noOp))
            .formLogin(form -> form.disable())
            .logout(logout -> logout.disable());

        // WebFlux default CSRF is kept;
        // demo exposes GET only, no state-changing endpoints.
        return http.build();
    }
}
```

Use `@EnableWebFluxSecurity` and `SecurityWebFilterChain`, **not** `@EnableWebSecurity` or Servlet `HttpSecurity`. `NoOpServerSecurityContextRepository` ensures HTTP Basic does not persist authentication to the next request. This lets us test that **each individual request** must supply valid Basic credentials; no session silently turns an uncredentialed request into authenticated.

Even though `HttpBasicSpec` has its own auth manager, the code also passes `noOp` to both the Basic filter and the chain so security context reading/saving stays consistent. When switching to stateful form login, `WebSessionServerSecurityContextRepository` and login success flow behave differently; never apply this article's stateless config to a browser-session system without evaluating CSRF.

`/admin` tests authorization additionally: when `alice` logs in via Basic successfully, she is a valid user yet **lacks ROLE_ADMIN**, so the request is rejected with `403`. This is an **authorization failure**, not the manager emitting `Mono.error(BadCredentialsException)`. Distinguishing the two stages is essential.

### 4.6. Controller with ReactiveSecurityContextHolder

**`src/main/java/example/reactivesignals/SignalController.java`**

```java
package example.reactivesignals;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class SignalController {

    @GetMapping("/public")
    public Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/private")
    public Mono<String> privatePage() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> "hello:"
                + context.getAuthentication().getName());
    }

    @GetMapping("/admin")
    public Mono<String> adminPage() {
        return Mono.just("admin");
    }
}
```

In WebFlux, `SecurityContext` is bound to the **Reactor Context**; you should not read ThreadLocal `SecurityContextHolder` and assume it keeps the identity after the pipeline switches schedulers. `ReactiveSecurityContextHolder.getContext()` is the proper API inside a reactor chain.

When `alice` authenticates successfully, GET `/private` returns the body:

```text
hello:alice
```

This is the **designed** body of the endpoint, not observed execution output. In larger APIs, enforce resource permissions, object ownership, and auditing alongside simple URL-based rules.

## 5. Unit Tests: Observing Signals Accurately with StepVerifier

`StepVerifier` lets you assert whether the publisher emitted an `Authentication`, completed empty, or terminated with `onError`. It is clearer than calling `.block()`, especially in reactive code where blocking the event loop is undesirable.

**`src/test/java/example/reactivesignals/ReactiveManagerSignalsTest.java`**

```java
package example.reactivesignals;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DelegatingReactiveAuthenticationManager;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

class ReactiveManagerSignalsTest {

    private final DemoReactiveAuthenticationManager manager =
        new DemoReactiveAuthenticationManager(new BCryptPasswordEncoder());

    private static Authentication request(String username, String password) {
        return UsernamePasswordAuthenticationToken.unauthenticated(
            username, password);
    }

    @Test
    void successEmitsOneVerifiedAuthenticationThenCompletes() {
        StepVerifier.create(manager.authenticate(
                request("alice", "study-pass")))
            .assertNext(result -> {
                assertTrue(result.isAuthenticated());
                assertInstanceOf(VerifiedPrincipal.class,
                    result.getPrincipal());

                VerifiedPrincipal principal =
                    (VerifiedPrincipal) result.getPrincipal();
                assertEquals("acct-101", principal.accountId());
                assertEquals("alice", principal.username());
                assertEquals("alice", result.getName());
                assertNull(result.getCredentials());

                Set<String> roles = result.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .collect(Collectors.toSet());
                assertEquals(Set.of("ROLE_USER"), roles);
            })
            .verifyComplete();
    }

    @Test
    void unsupportedTokenCompletesEmptyWithoutOnNext() {
        Authentication otherMechanism = new AnonymousAuthenticationToken(
            "demo-key", "guest",
            List.of(new SimpleGrantedAuthority("ROLE_ANONYMOUS")));

        StepVerifier.create(manager.authenticate(otherMechanism))
            .verifyComplete(); // No onNext, no onError.
    }

    @Test
    void wrongPasswordProducesAuthenticationError() {
        StepVerifier.create(manager.authenticate(
                request("alice", "wrong")))
            .expectError(BadCredentialsException.class)
            .verify();
    }

    @Test
    void unknownUserAlsoProducesAuthenticationError() {
        StepVerifier.create(manager.authenticate(
                request("not-alice", "study-pass")))
            .expectError(BadCredentialsException.class)
            .verify();
    }

    @Test
    void missingCredentialIsAnErrorNotEmpty() {
        StepVerifier.create(manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "alice", null)))
            .expectError(BadCredentialsException.class)
            .verify();
    }

    @Test
    void emptyCanDelegateToAnotherManager() {
        ReactiveAuthenticationManager abstain = ignored -> Mono.empty();
        DelegatingReactiveAuthenticationManager chain =
            new DelegatingReactiveAuthenticationManager(abstain, manager);

        StepVerifier.create(chain.authenticate(
                request("alice", "study-pass")))
            .assertNext(result -> {
                assertTrue(result.isAuthenticated());
                assertEquals("alice", result.getName());
            })
            .verifyComplete();
    }

    @Test
    void aFailureIsNotSilentlyTurnedIntoSuccess() {
        ReactiveAuthenticationManager reject = ignored ->
            Mono.error(new BadCredentialsException("Invalid credentials"));

        StepVerifier.create(reject.authenticate(
                request("alice", "study-pass")))
            .expectError(BadCredentialsException.class)
            .verify();
    }
}
```

**Expected result:** **7 `@Test`s** total. Meaningful assertions:

- `assertNext(...).verifyComplete()` guarantees **exactly one Authentication**, followed by normal completion, while checking the server-supplied principal and authorities.
- `verifyComplete()` right after subscribing confirms **zero items** and no error; that is `Mono.empty()`.
- `expectError(BadCredentialsException.class)` ensures **no success and no empty completion**, but an `onError` signal of the exact type.
- `DelegatingReactiveAuthenticationManager` shows a manager that does not handle a request type deferring to another manager. By default, errors from a delegate are not treated as empty; configuring `continueOnError` (if used) must be reviewed very strictly.
- Unit tests invoke the manager directly; they do **not** verify HTTP responses. The next section tests the real filter and authorization.

## 6. WebTestClient: Observing 200, 401, and 403 Over HTTP

At the HTTP layer, there is **no one-to-one mapping** from every Reactor signal to a fixed status code; it depends on the filter, entry point, failure handler, and authorization. With the example's HTTP Basic configuration, we can write concrete tests:

**`src/test/java/example/reactivesignals/ReactiveHttpSignalsTest.java`**

```java
package example.reactivesignals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveHttpSignalsTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointWorksWithoutCredentials() {
        client.get().uri("/public").exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void validBasicCredentialsReturn200() {
        client.get().uri("/private")
            .headers(headers -> headers.setBasicAuth("alice", "study-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("hello:alice");
    }

    @Test
    void badCredentialsReturn401() {
        client.get().uri("/private")
            .headers(headers -> headers.setBasicAuth("alice", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void absentCredentialsTriggerAuthenticationEntryPoint() {
        client.get().uri("/private")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void validUserWithoutAdminRoleGets403() {
        client.get().uri("/admin")
            .headers(headers -> headers.setBasicAuth("alice", "study-pass"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void statelessBasicDoesNotPersistAuthenticationAcrossRequests() {
        client.get().uri("/private")
            .headers(headers -> headers.setBasicAuth("alice", "study-pass"))
            .exchange()
            .expectStatus().isOk();

        // New request does not send credentials: must be challenged.
        client.get().uri("/private")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

There are **6 `@Test`s** in the HTTP test class, totaling **13 tests** across both classes.

| Request | What is happening | Expected response with example config |
| --- | --- | --- |
| GET `/public` without Authorization | `permitAll()` | `200` |
| GET `/private`, valid Basic | Manager emits verified Authentication | `200` and `hello:alice` |
| GET `/private`, wrong Basic | Manager emits `BadCredentialsException` | `401` via Basic failure handler |
| GET `/private`, no header | Converter creates no auth request; authorization requires login | `401` via Basic entry point |
| GET `/admin`, alice's valid Basic | Authenticated, but lacks `ROLE_ADMIN` | `403` Forbidden |
| GET `/private`, second request without Basic | No-op repo, does not persist auth across requests | `401` |

**Do not conclude** that “a manager's `Mono.empty()` always equals HTTP 401” from the missing-header test. The missing-header case **never invokes the manager**, because the converter produces no token. To test manager empty at the HTTP level, you must build a converter producing the token type sent to a manager that returns empty and define the chain/entry point behavior; that is beyond the demo Basic API and should not be assumed.

### Commands to Run

From a project root with the Gradle wrapper:

```bash
./gradlew test --tests example.reactivesignals.ReactiveManagerSignalsTest
./gradlew test --tests example.reactivesignals.ReactiveHttpSignalsTest
./gradlew bootRun
```

On Windows use `gradlew.bat`. The examples are written for Spring Security 6.x and Java 17; the results above are **expected assertions**, not an execution report in this document. The HTTP tests start an embedded server on a random port; the manager tests do not need an HTTP server.

## 7. When Multiple Authentication Managers Exist

An application may support multiple request types: Basic username/password, bearer JWT, API key, or client certificate. Managers do **not** have to inspect the same `Authentication` type. When designing a composite manager, one manager can say “I do not handle this type” with `Mono.empty()` and let the next manager handle it.

```text
Incoming Authentication
         |
         v
DelegatingReactiveAuthenticationManager
         |
         +-- manager A: username/password?
         |     |- matching type: verify
         |     |    |- success -> Authentication
         |     |    '-- failure -> AuthenticationException
         |     '-- other type: Mono.empty()
         |
         +-- manager B: API key?
         |     |- matching type: verify
         |     '-- other type: Mono.empty()
         |
         '-- manager C: JWT?
               |- matching type: verify signature, issuer, audience, exp...
               '-- other type: Mono.empty()
```

Pitfalls to avoid:

1. If manager A **already** determined the password is wrong yet returns empty, another manager might be tried and accidentally accept an unintended authentication path.
2. If manager A returns an error for **every unfamiliar token**, downstream managers handling JWT/API keys might never be tried, wrongly rejecting valid mechanisms.
3. Do not enable `setContinueOnError(true)` just to make “login easier”: across different managers, continuing after an error can weaken security boundaries. Check the API/version and threat model before changing the default.
4. If every manager returns empty, there is no proof of successful authentication. The filter/entry point must handle that case per policy; never synthesize a default `ROLE_USER` for the request.
5. Classify by **token type and valid matcher**, not by trusting a client-supplied `type=admin` or `role=ADMIN` field without verification.
6. With multiple `SecurityWebFilterChain` beans, matchers and chain order decide which mechanism runs. AuthenticationManager only evaluates the token passed by that chain's filter. Do not use a broad fallback manager that accidentally accepts any credential.

### When the Reactive User Store Returns Mono.empty

A `ReactiveUserDetailsService.findByUsername("missing")` or reactive repository can return `Mono.empty()` to indicate **no record found**. Yet if the manager has committed to handling username/password tokens, failing to find the user is an **authentication failure**, not “manager does not support”.

Pseudo-code example:

```java
Mono<Authentication> findAndVerify(
        String username, String rawPassword) {

    return reactiveDirectory.findByUsername(username)
        .switchIfEmpty(Mono.error(
            new BadCredentialsException("Invalid credentials")))
        .flatMap(account -> verifyPasswordAndBuildAuthentication(
            account, rawPassword));
}
```

Here `reactiveDirectory` and `verifyPasswordAndBuildAuthentication` are **hypothetical application APIs**, not built-in classes/libraries. The key idea is that a **repository empty** should be converted into an **AuthenticationException** once a username/password request has been accepted for handling by the manager.

For reactive SQL databases, use R2DBC/reactive repositories to avoid blocking queries on Netty. If using blocking JDBC/LDAP, use proper schedulers/offloading with timeouts, pools/backpressure; never call `.block()` in the request chain. I/O errors or database downtime must not silently become wrong password; never let the system “fail open” with a default principal when the identity source is unreachable.

## 8. Error Handling Strategy: Fail Closed Without Leaking Internals

### 8.1. Authentication Failure vs. Backend Failure

| Scenario | Meaning | How to express |
| --- | --- | --- |
| Wrong password | Invalid proof | `Mono.error(new BadCredentialsException("Invalid credentials"))` |
| Nonexistent username (in username/password provider) | Identity not proven | `Mono.error(BadCredentialsException)`, avoid enumeration |
| Account locked | Account state disallows login | `Mono.error(new LockedException(...))` or appropriate exception |
| Token outside manager's supported type | Manager abstains | `Mono.empty()` |
| Valid credentials and account permitted to log in | Authentication succeeded | `Mono.just(authenticatedToken)` or `Mono.fromCallable(...)` emitting token |
| Database/IdP network error | Cannot verify safely due to infra failure | `onError`, classify separately; never default to authenticated |

Error messages returned to clients should be informative enough without disclosing whether a username exists, hashes, IdP configuration details, or credentials. Server logs/audits can categorize errors safely with request IDs and timestamps, **never logging raw Authorization headers/passwords/tokens**.

In HTTP Basic/WebFlux, `AuthenticationException` is typically turned into a `401` challenge by the failure handler. Other errors such as I/O or programming errors may flow to the server's exception handler and produce `5xx`; do not promise a uniform status code unless explicitly configured. What matters is never converting backend errors into `Mono.empty()` as if the request needed no authentication.

### 8.2. How Error Types Affect Operators

With a `Mono<Authentication>` publisher, operator order changes the outcome:

```java
Mono<Authentication> source = authenticateSupportedRequest(token);

// If source is EMPTY, remains empty and mapper is not called.
Mono<Authentication> mapped = source.map(auth -> auth);

// If source is ERROR, error still propagates.
Mono<Authentication> notEmptyFallback =
    source.switchIfEmpty(Mono.error(
        new BadCredentialsException("No result for supported request")));

// Catch errors only when intentionally designing a specific failure policy.
Mono<Authentication> explicitFailure = source.onErrorMap(
    UnavailableIdentityStoreException.class,
    ex -> new AuthenticationServiceException(
        "Authentication service unavailable", ex));
```

Here `UnavailableIdentityStoreException` is an **example application exception name**, not provided by Spring Security. These snippets illustrate Reactor operators, not complete methods to copy into a project. To compile, provide that exception class or replace it with a real infrastructure exception.

**Never** add `onErrorResume(ignored -> Mono.just(adminToken))` to “ensure login always works,” as that is a critical authentication vulnerability. Do not use `onErrorComplete()` across the authentication chain if it silently turns wrong passwords or identity store failures into empty.

## 9. Checking Reactor Context and Lifecycle

### 9.1. Cold Publishers and Verification Timing

`Mono.fromCallable(...)` runs its work **when actually subscribed to**. Therefore:

```java
Mono<Authentication> mono = manager.authenticate(
    UsernamePasswordAuthenticationToken.unauthenticated(
        "alice", "study-pass"));

// Creating the Mono does not guarantee password has been checked yet.
// StepVerifier / WebFlux filter will subscribe to the chain.
```

Do not place dangerous side effects at publisher-creation time if they are meant to run only when a filter starts the attempt; and do not subscribe manually inside the manager. **Return the publisher** so the framework manages subscription, backpressure, cancellation, and context.

### 9.2. ReactiveSecurityContextHolder Instead of ThreadLocal

In WebFlux, a succeeding filter stores the Authentication in the **Reactor Context**, so downstream endpoints can read it via `ReactiveSecurityContextHolder`. Because threads can switch after `publishOn`/`subscribeOn`, do not use ThreadLocal `SecurityContextHolder.getContext()` as in Servlet to identify the user in a reactive pipeline.

```java
return ReactiveSecurityContextHolder.getContext()
    .map(security -> security.getAuthentication())
    .map(Authentication::getName);
```

This pattern is useful inside controllers/services actually running within the reactive chain. In direct manager unit tests, there is no HTTP filter context automatically storing identity; tests only inspect the publisher and result object. Do not confuse “manager emitted Authentication” with “browser has a session cookie” or “context persisted for the next request”.

### 9.3. Cancel Does Not Mean Login Failure

Reactive Streams also have **cancel** caused by client disconnects, timeouts, or downstream unsubscribing. Cancel is neither `Mono.empty()` nor `Mono.error()` in the sense of normal publisher completion; it is subscription cancellation. For metrics, use `doFinally(signalType)` to distinguish `ON_COMPLETE`, `ON_ERROR`, and `CANCEL`, avoiding logging “login success” merely because the chain stopped.

In all cases, a downstream subscriber cancelling must never cause the manager to emit an unverified authentication. Context storage, auditing, and credential issuance must tie to the success handler and safe transactional/side-effect boundaries.

## 10. Summary of Mistakes and Fixes

| Wrong or incomplete pattern | Problem | Correct approach |
| --- | --- | --- |
| `return null;` from `ReactiveAuthenticationManager` | Violates publisher contract | Return `Mono.empty()`, `Mono.error(...)`, or `Mono<Authentication>` |
| `Mono.just(null)` | Reactor forbids null onNext | Use `Mono.empty()` when there is no result |
| `return Mono.empty()` on wrong password | Drops failure signal, may try another manager | `Mono.error(BadCredentialsException)` |
| `return Mono.error(BadCredentialsException)` for other token types | Blocks other auth paths even though manager does not support it | `Mono.empty()` for out-of-scope token types |
| `return Mono.just(requestToken)` before verification | Legitimizes unverified credentials | Construct `authenticated(...)` after verification |
| Copying `request.getAuthorities()` | Client can supply fake authority claims | Map roles from verified server/issuer source |
| `doOnSuccess(auth -> logSuccess())` without checking auth | Empty completion invokes callback with null | Use `doOnNext` or check actual non-null value |
| `switchIfEmpty(...)` thinking it catches errors | Does not intercept `onError` | Use dedicated error operators, preserving security semantics |
| `onErrorResume(ex -> Mono.empty())` for all errors | Hides wrong passwords and outages | Classify errors, fail closed |
| `block()` on the Netty event loop | Can fail or stall the reactive server | Return publisher; use reactive I/O or proper offloading |
| Using ThreadLocal `SecurityContextHolder` in WebFlux | Context may be lost across scheduler hops | `ReactiveSecurityContextHolder` |
| Concluding missing Basic header means manager returned empty | Converter usually produced no token; manager was not called | Test converter and manager separately |
| Inferring every empty = 401 from HTTP tests | Response depends on filter/composition/entry point | Test StepVerifier contract and concrete HTTP flow |
| Returning authenticated fallback when IdP/database fails | Fail open, privilege escalation risk | Emit error and deny authentication |
| Logging raw passwords/tokens/Authorization headers | Credential leak | Redact and log minimal metadata |

## 11. Self-Check Checklist

- [ ] Manager emits `Mono<Authentication>` with verified principal/authorities on success.
- [ ] Out-of-scope token types return `Mono.empty()`, not a bogus “wrong password” error.
- [ ] Wrong password, nonexistent username, or malformed supported credentials return `Mono.error(AuthenticationException)`.
- [ ] Reactive data store returning empty is converted into an authentication failure in the manager handling that token.
- [ ] Infrastructure errors are not turned into success/empty; the application fails closed.
- [ ] Never emits null, never trusts request-supplied authorities, and never treats an unauthenticated token as success.
- [ ] `StepVerifier` tests verify success (1 onNext), empty (0 onNext), and error (onError) separately.
- [ ] `ServerAuthenticationConverter Mono.empty()` and `ReactiveAuthenticationManager Mono.empty()` are not confused.
- [ ] HTTP tests verify 200 for valid credentials, 401 for missing/wrong credentials, and 403 when authenticated without required role.
- [ ] `switchIfEmpty`, `onErrorResume`, and `doOnSuccess` are used with exact semantics; no suppressed security errors.
- [ ] No `block()` on the event loop; BCrypt/blocking I/O checks are offloaded or use reactive sources properly.
- [ ] WebFlux uses `SecurityWebFilterChain` and `ReactiveSecurityContextHolder`; does not copy Servlet filter chains.
- [ ] Real applications verify TLS/timeouts/cancellation, observability, rate limiting, and account enumeration controls.

### Official Documentation

- [Spring Security 6.5 — ReactiveAuthenticationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html)
- [Spring Security 6.5 — AuthenticationWebFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html)
- [Spring Security 6.5 — DelegatingReactiveAuthenticationManager](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/DelegatingReactiveAuthenticationManager.html)
- [Spring Security 6.5 — ServerHttpSecurity API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Security — WebFlux Security Reference](https://docs.spring.io/spring-security/reference/6.5/reactive/index.html)
- [Spring Security — Reactive Security Context](https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/index.html)
- [Project Reactor — Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
