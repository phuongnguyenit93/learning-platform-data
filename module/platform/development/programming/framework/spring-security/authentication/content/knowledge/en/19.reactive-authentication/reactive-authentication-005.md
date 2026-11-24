# DelegatingReactiveAuthenticationManager and Coordinating Multiple Managers in Spring Security WebFlux

## 1. Lesson Objectives

A **Spring Security WebFlux** application can support multiple authentication mechanisms simultaneously: username/password, service-account API keys, JWT bearer tokens, opaque tokens, or a custom challenge. Each mechanism has its own `Authentication` type, credential verification logic, identity store, and error rules. Rather than writing a giant `if/else` block or accidentally letting every manager handle every token, Spring Security provides **`DelegatingReactiveAuthenticationManager`** to coordinate multiple `ReactiveAuthenticationManager` instances in order.

After completing this lesson, you will be able to:

1. Understand the `ReactiveAuthenticationManager.authenticate(Authentication)` contract returning `Mono<Authentication>`.
2. Clearly distinguish **`Mono.just(authenticated)`**, **`Mono.empty()`**, and **`Mono.error(AuthenticationException)`**.
3. Use `DelegatingReactiveAuthenticationManager` to pick the right manager for a token type and fall back when an earlier manager **cannot determine** an outcome.
4. Understand the default **`setContinueOnError(false)`** and why setting it to `true` can introduce fallback vulnerabilities if misconfigured.
5. Build a dedicated API key manager and combine it with a username/password manager without mixing up credential verification responsibilities.
6. Wire the composite manager with `AuthenticationWebFilter` and `ServerAuthenticationConverter` in a Servlet-free WebFlux system.
7. Know when to choose `ReactiveAuthenticationManagerResolver` or multiple `SecurityWebFilterChain` beans instead of one delegating manager.
8. Write Reactor `StepVerifier` tests verifying ordering, fallback, errors, cancellation, and authentication results.

Examples use **Java 17+, Spring Security 6.5.x, Reactor 3.x, and Maven**. The main hands-on exercise is a **runnable Java program** without a web server, followed by WebFlux integration guidance. This is not Servlet `AuthenticationManager` / `UsernamePasswordAuthenticationFilter` code.

## 2. The Big Picture

A WebFlux request is converted into an unauthenticated token, then handed to a reactive manager:

~~~text
HTTP request
      |
      v
Spring WebFlux / SecurityWebFilterChain
      |
      v
AuthenticationWebFilter
      |
      v
ServerAuthenticationConverter.convert(exchange)
      |
      +-- Mono.empty() => no authentication request for this filter
      |
      +-- Mono.error(...) => parse/conversion error
      |
      +-- Unauthenticated Mono<Authentication>
                    |
                    v
        DelegatingReactiveAuthenticationManager
                    |
        +-----------+-----------+
        |                       |
        v                       v
 API key manager         Password manager
 (1st manager)            (2nd manager)
        |                       |
        +-- Mono.empty() ------>+-- handle password token
        |                       |
        +-- Mono.just(...)      +-- Mono.just(...)
        |      |                        |
        |      +---- success -----------+
        |
        +-- Mono.error(...) -> default error, no fallback
                    |
                    v
        AuthenticationWebFilter
         +-- success handler, security context
         +-- failure handler for AuthenticationException
                    |
                    v
           Authorization / controller
~~~

**Three distinct layers:**
- **Converter** asks: does this HTTP request carry credentials for a mechanism I support? If not, it can return `Mono.empty()` **before any manager is called**.
- **Manager** asks: does this `Authentication` object belong to my protocol? If not, return `Mono.empty()` so the next manager can examine it. If yes but the credentials are invalid, return `Mono.error(...)`.
- **Delegator** only coordinates multiple managers; it does **not** verify passwords, decode JWTs, or determine roles itself. Authority results must come from the manager that verified the identity.

## 3. The ReactiveAuthenticationManager Contract

Spring Security's core interface:

~~~java
@FunctionalInterface
public interface ReactiveAuthenticationManager {
    Mono<Authentication> authenticate(Authentication authentication);
}
~~~

Outcome semantics:

| Outcome of a single manager | Interpretation | Default delegating manager |
| --- | --- | --- |
| `Mono.just(authenticatedResult)` | Manager authenticated successfully and returned a trusted identity | Stops; returns this result |
| `Mono.empty()` | Manager cannot decide, e.g., unsupported token type | Continues trying the next manager |
| `Mono.error(new BadCredentialsException(...))` | Manager owns the token type, but credentials are invalid | Stops and propagates the error by default |
| `Mono.error(new AuthenticationServiceException(...))` | Authentication system / data source error | Propagates the error by default; does not pretend empty |
| `Mono.just(unauthenticatedToken)` | Contract violation if treated as success | Must avoid; emit authenticated tokens only after verification |

**Do not confuse `null` with `Mono.empty()`.** Reactive methods must return a valid `Mono`; never write `return null;`. When an `Authentication` type is unsupported, use `Mono.empty()`.

**Do not confuse `Mono.empty()` with “wrong password”.** If you accept your own username/password token and find the password wrong, return `Mono.error(new BadCredentialsException(...))`. Turning a bad-credential failure into empty so another manager runs can create a bypass that accepts previously rejected credentials.

### Laziness of Mono

Most Reactor pipelines are **lazy**: calling `authenticate(...)` builds the publisher, while logic inside `Mono.defer(...)` or `Mono.fromCallable(...)` runs upon **subscription**. `AuthenticationWebFilter` subscribes as part of the request flow. In tests, `StepVerifier` is the subscriber; in a simple CLI program, `block()` is used **only at the CLI entry point**.

Never call `block()`, `blockOptional()`, `Thread.sleep()`, or blocking JDBC directly on WebFlux's Netty event loop. When integrating a blocking data source, use bounded offloading with load control; ideally, use a reactive driver/repository.

## 4. How Does DelegatingReactiveAuthenticationManager Work?

Spring Security 6.5 provides constructors:

~~~java
new DelegatingReactiveAuthenticationManager(
    apiKeyManager,
    passwordManager
);

// Or a List in exact order:
new DelegatingReactiveAuthenticationManager(
    List.of(apiKeyManager, passwordManager)
);
~~~

It takes **`ReactiveAuthenticationManager` instances in the supplied order**. Official documentation states:

- When `continueOnError=false` (the default), it tries managers until the **first non-empty result**; an error is not automatically treated as “unsupported”.
- When `continueOnError=true`, it continues until the **first result that is both non-empty and error-free**. This changes fallback policy when a manager emits `Mono.error`.
- `setContinueOnError(boolean)` was introduced in Spring Security 6.3; verify your version when applying to older codebases.

### Example with Typed Tokens

~~~text
Delegates: [ApiKeyManager, PasswordManager]

Case A: ApiKeyAuthenticationToken("valid")
  ApiKeyManager -> Mono.just(authenticated)
  PasswordManager is not called

Case B: UsernamePasswordAuthenticationToken("alice", password)
  ApiKeyManager -> Mono.empty()
  PasswordManager -> Mono.just(authenticated)

Case C: ApiKeyAuthenticationToken("wrong-key")
  ApiKeyManager -> Mono.error(BadCredentialsException)
  PasswordManager is NOT tried by default

Case D: An Authentication type neither recognizes
  ApiKeyManager -> Mono.empty()
  PasswordManager -> Mono.empty()
  Neither manager can determine a result
~~~

Order matters greatly when **multiple managers support the same token type**. Once an earlier manager succeeds, later managers are not invoked to “add” authorities. The delegating manager never merges two identities or sums authorities; it seeks **one** complete authentication result.

### Why Use a Dedicated Token Class per Protocol?

If you reuse `UsernamePasswordAuthenticationToken` to carry API keys, OTPs, and SSO codes, multiple managers may accept the same token class while interpreting credentials differently. Unintended fallbacks happen easily—for example, manager A rejects a username/password, yet manager B interprets the password as an API token.

Good design:
- `ApiKeyAuthenticationToken` for API keys; manager A checks only this class.
- `UsernamePasswordAuthenticationToken` for username/password; manager B checks only this class.
- `JwtAuthenticationToken` or resource-server JWT authentication tokens routed to a dedicated manager/decoder.

A specific token class makes the credential type part of the **authentication contract**, instead of guessing from string formats or arbitrary headers at the manager layer.

## 5. “Unsupported” Differs from “Failure”

Condensed Java example for a manager that understands only API key tokens:

~~~java
@Override
public Mono<Authentication> authenticate(Authentication candidate) {
    if (!(candidate instanceof ApiKeyToken request)) {
        return Mono.empty(); // Not a type this manager handles.
    }

    return Mono.defer(() -> {
        if (!isValidKey(request)) {
            return Mono.error(
                new BadCredentialsException("Invalid credentials"));
        }
        return Mono.just(verifiedServiceAuthentication(request));
    });
}
~~~

**This is an illustrative snippet** without defining `ApiKeyToken`, `isValidKey`, or `verifiedServiceAuthentication`; the full runnable version is in Section 7.

Common mistakes:

~~~java
// WRONG: every invalid credential becomes "unknown".
return verifyKey(input)
    .onErrorResume(error -> Mono.empty());

// WRONG: token is not a supported type, yet attempts to cast.
ApiKeyToken key = (ApiKeyToken) authentication;

// WRONG: one manager accepts everything without checking token class.
if (authentication.getCredentials() != null) {
    return Mono.just(authentication);
}

// WRONG: builds an authenticated Authentication before actually verifying.
return Mono.just(
    UsernamePasswordAuthenticationToken.authenticated(
        request.getPrincipal(), null, request.getAuthorities()));
~~~

Do not use `onErrorResume(e -> Mono.empty())` as a “crash-prevention trick”: it hides errors and turns invalid credentials or internal failures into fallbacks to later managers. Especially avoid letting a later permissive manager grant access that an earlier manager rejected.

## 6. Rules for Choosing Order and Safe Fallback

### Which Manager Should Come First?

If managers have **non-overlapping token types**, ordering has little impact on outcomes, though it still affects metrics, logging, and publisher allocation cost. Usually put specialized, cheap, and high-frequency managers first; avoid expensive I/O just to discover a token is the wrong type.

If multiple managers can handle the same token type:
1. Document clearly who owns verification for that token.
2. Use a verified issuer, tenant, client ID, or resource scope to select one valid manager.
3. Ensure earlier managers never “pass on” invalid credentials via `Mono.empty()`.
4. Test behavior when the first manager succeeds, fails, finds no identity, or hits a backend error.
5. Avoid `continueOnError=true` unless a security review and tests prove the fallback is safe.

### Why Is continueOnError=true Dangerous?

Suppose manager A validates tenant A's API keys and emits `BadCredentialsException` when a key is wrong. Manager B also accepts the same token type with weaker logic or a stale credential copy. If you enable:

~~~java
DelegatingReactiveAuthenticationManager manager =
    new DelegatingReactiveAuthenticationManager(managerA, managerB);
manager.setContinueOnError(true);
~~~

then when manager A errors, the delegator **can continue** to manager B and accept its result. That is the **intended behavior of the option**, not a Spring Security bug. However, the application must justify why an error from A is allowed to fall through to B. In most multi-protocol authentication setups, keep the default `false` and separate token types cleanly.

**Do not misunderstand:** `setContinueOnError(true)` does not overwrite an earlier manager's authenticated result with a later manager's result. It only changes error handling. Once any manager succeeds, the delegator stops and returns the first success.

### The “Not My Responsibility” Case

If manager A accepts only API keys and receives a username/password token, returning `Mono.empty()` is right. If manager A receives an API key whose record does not exist and policy defines that as an invalid API key, it should normally return `Mono.error(BadCredentialsException)` rather than yielding to other managers. If managing multiple key stores with approved fallback, a single dispatcher/manager with explicit routing rules is safer.

## 7. Runnable Java 17 Exercise

This exercise designs **two separate `ReactiveAuthenticationManager` implementations**:
- `ApiKeyManager`: accepts `ApiKeyToken`; verifies a demo key; returns `ROLE_SERVICE`.
- `PasswordManager`: accepts `UsernamePasswordAuthenticationToken`; verifies a demo password via BCrypt; returns `ROLE_USER`.

Both managers are wired into `DelegatingReactiveAuthenticationManager` in order. The CLI program uses `block()` in `main` solely to print outputs; in a real WebFlux system, **never use `block()` on request threads**.

Keys, usernames, and passwords below are **lesson data only**. Production must load accounts from trusted stores with hash/secret management, tenant isolation, account statuses, rate limiting, and safe auditing. Never hardcode credentials in real apps.

### 7.1. Project Structure

~~~text
reactive-delegating-demo/
├── pom.xml
└── src/
    ├── main/java/demo/reactive/ReactiveManagersDemo.java
    └── test/java/demo/reactive/ReactiveManagersDemoTest.java
~~~

### 7.2. Maven

`pom.xml`. The Spring Boot BOM is used solely to align dependency versions; **no web server is started** in the CLI:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>reactive-delegating-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-core</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-crypto</artifactId>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.3. Complete Source Code

Create `src/main/java/demo/reactive/ReactiveManagersDemo.java`:

~~~java
package demo.reactive;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Collection;
import java.util.List;

import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DelegatingReactiveAuthenticationManager;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public final class ReactiveManagersDemo {

    private ReactiveManagersDemo() {
    }

    /**
     * Authentication token dedicated to API keys.
     * final so the supported token type cannot silently change via subclassing.
     */
    public static final class ApiKeyToken
            extends AbstractAuthenticationToken {

        private final Object principal;
        private String apiKey;

        private ApiKeyToken(
                Object principal,
                String apiKey,
                Collection<? extends GrantedAuthority> authorities,
                boolean authenticated) {

            super(authorities);
            this.principal = principal;
            this.apiKey = apiKey;
            // Private factory controls creating authenticated tokens.
            super.setAuthenticated(authenticated);
        }

        public static ApiKeyToken unauthenticated(String key) {
            return new ApiKeyToken(
                "unverified-service", key, List.of(), false);
        }

        private static ApiKeyToken verified(String serviceName) {
            return new ApiKeyToken(
                serviceName,
                null, // Do not carry secret onto the success token.
                List.of(new SimpleGrantedAuthority("ROLE_SERVICE")),
                true);
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
            this.apiKey = null;
        }

        @Override
        public void setAuthenticated(boolean authenticated) {
            if (authenticated) {
                throw new IllegalArgumentException(
                    "Unverified token cannot be marked trusted");
            }
            super.setAuthenticated(false);
        }
    }

    /**
     * First manager: ONLY knows ApiKeyToken.
     */
    public static final class ApiKeyManager
            implements ReactiveAuthenticationManager {

        private static final String DEMO_KEY = "demo-service-key";

        @Override
        public Mono<Authentication> authenticate(Authentication candidate) {
            // Do not cast and do not error on unfamiliar tokens.
            if (!(candidate instanceof ApiKeyToken request)) {
                return Mono.empty();
            }

            // defer: verification runs only on subscription.
            return Mono.defer(() -> {
                if (request.isAuthenticated()
                        || !(request.getCredentials()
                             instanceof String supplied)
                        || supplied.isBlank()) {

                    return Mono.error(
                        new BadCredentialsException(
                            "Invalid credentials"));
                }

                byte[] expected =
                    DEMO_KEY.getBytes(StandardCharsets.UTF_8);
                byte[] actual =
                    supplied.getBytes(StandardCharsets.UTF_8);

                if (!MessageDigest.isEqual(expected, actual)) {
                    return Mono.error(
                        new BadCredentialsException(
                            "Invalid credentials"));
                }

                // Only emit trusted principal after successful verification.
                return Mono.just(
                    (Authentication) ApiKeyToken.verified(
                        "service-client"));
            });
        }
    }

    /**
     * Second manager: ONLY knows username/password.
     * BCrypt runs off the event-loop in the demo.
     */
    public static final class PasswordManager
            implements ReactiveAuthenticationManager {

        private final PasswordEncoder encoder =
            new BCryptPasswordEncoder();

        // Demo: created once when constructing manager.
        // Production reads stable stored password hashes from DB/IdP.
        private final String passwordHash =
            encoder.encode("learn-password");

        @Override
        public Mono<Authentication> authenticate(Authentication candidate) {
            if (!(candidate instanceof UsernamePasswordAuthenticationToken
                    request)) {
                return Mono.empty();
            }

            return Mono.fromCallable(() -> {
                if (request.isAuthenticated()
                        || !"alice".equals(request.getPrincipal())
                        || !(request.getCredentials()
                             instanceof String password)
                        || !encoder.matches(password, passwordHash)) {

                    throw new BadCredentialsException(
                        "Invalid credentials");
                }

                return (Authentication)
                    UsernamePasswordAuthenticationToken.authenticated(
                        "alice",
                        null,
                        List.of(
                            new SimpleGrantedAuthority("ROLE_USER")
                        )
                    );
            }).subscribeOn(Schedulers.boundedElastic());
        }
    }

    public static ReactiveAuthenticationManager manager() {
        return new DelegatingReactiveAuthenticationManager(
            new ApiKeyManager(),
            new PasswordManager()
        );
    }

    public static void main(String[] args) {
        ReactiveAuthenticationManager manager = manager();

        // ONLY CLI uses block to print results.
        Authentication api = manager.authenticate(
            ApiKeyToken.unauthenticated("demo-service-key")
        ).block();

        Authentication password = manager.authenticate(
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "learn-password")
        ).block();

        System.out.println("api-principal=" + api.getName());
        System.out.println("api-authenticated=" + api.isAuthenticated());
        System.out.println("password-principal=" + password.getName());
        System.out.println(
            "password-authenticated=" + password.isAuthenticated());

        try {
            manager.authenticate(
                ApiKeyToken.unauthenticated("wrong-key")
            ).block();
        } catch (BadCredentialsException ex) {
            System.out.println(
                "bad-key=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

### 7.4. Run Command and Output

In the project directory (with JDK 17+ and Maven installed):

~~~bash
mvn -q -DskipTests compile
mvn -q -Dexec.mainClass=demo.reactive.ReactiveManagersDemo exec:java
~~~

Lines **explicitly printed by the program**:

~~~text
api-principal=service-client
api-authenticated=true
password-principal=alice
password-authenticated=true
bad-key=BadCredentialsException
~~~

Maven/Logback/Reactor may emit additional log lines or warnings depending on your environment. The `bad-key` line illustrates the key rule: a wrong API key emits `Mono.error` and is not forwarded to `PasswordManager` under the default configuration.

**Important note:** the program uses `block()` in `main` to wait for the results and print to stdout. That is acceptable in a **command-line application**, not a pattern to deploy inside the WebFlux HTTP event-loop.

### 7.5. Why Does the Example Satisfy the Contract?

**Token differentiation by class.** `ApiKeyManager` checks `instanceof ApiKeyToken`. `PasswordManager` checks `instanceof UsernamePasswordAuthenticationToken`. Thus password requests are properly yielded by the first manager via `Mono.empty()`.

**Not confusing bad credentials with unsupported.** When `ApiKeyToken` carries an invalid key, `ApiKeyManager` returns `Mono.error(BadCredentialsException)`. No other manager is allowed to “salvage” the failure by interpreting those bad credentials under another protocol.

**Trusted server-side output.** Input tokens are always created with `authenticated=false`. After verification, the server selects `principal` and `authorities`. Client-sent roles or headers are never trusted.

**Separating secrets from results.** `ApiKeyToken.verified(...)` and `UsernamePasswordAuthenticationToken.authenticated(...)` return `null` credentials. When credentials must be held on the request token, keep their lifetime short and never log their values.

**Reactor is not blocked by BCrypt on the event-loop.** `PasswordManager` schedules `matches(...)` onto `Schedulers.boundedElastic()`. This illustrates the concept; production still needs rate limiting and concurrency bounds on authentications, or should use the built-in reactive manager via the standard flow rather than rolling custom password handling.

**Does not use Servlet's synchronous `AuthenticationManager`.** The entire delegator works with `Mono<Authentication>` rather than returning synchronous results to a WebFlux filter.

## 8. Testing with Reactor StepVerifier

The most important tests verify not just “the manager returns a principal,” but **the invocation order of delegates** and **the ability to distinguish empty from error**.

File `src/test/java/demo/reactive/ReactiveManagersDemoTest.java`:

~~~java
package demo.reactive;

import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DelegatingReactiveAuthenticationManager;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

class ReactiveManagersDemoTest {

    private static Authentication apiRequest(String key) {
        return ReactiveManagersDemo.ApiKeyToken.unauthenticated(key);
    }

    private static Authentication passwordRequest(String password) {
        return UsernamePasswordAuthenticationToken.unauthenticated(
            "alice", password);
    }

    @Test
    void apiKeyIsAuthenticatedByFirstManager() {
        StepVerifier.create(
            ReactiveManagersDemo.manager().authenticate(
                apiRequest("demo-service-key")))
            .assertNext(auth -> {
                assertEquals("service-client", auth.getName());
                assertTrue(auth.isAuthenticated());
                assertNull(auth.getCredentials());
                assertTrue(auth.getAuthorities().stream().anyMatch(
                    a -> a.getAuthority().equals("ROLE_SERVICE")));
            })
            .verifyComplete();
    }

    @Test
    void passwordFallsThroughFirstManagerToSecond() {
        StepVerifier.create(
            ReactiveManagersDemo.manager().authenticate(
                passwordRequest("learn-password")))
            .assertNext(auth -> {
                assertEquals("alice", auth.getName());
                assertTrue(auth.isAuthenticated());
                assertTrue(auth.getAuthorities().stream().anyMatch(
                    a -> a.getAuthority().equals("ROLE_USER")));
            })
            .verifyComplete();
    }

    @Test
    void unsupportedTypeReturnsEmptyInsteadOfCastError() {
        var foreign = new AnonymousAuthenticationToken(
            "test-key", "guest",
            List.of(new SimpleGrantedAuthority("ROLE_GUEST")));

        StepVerifier.create(
            ReactiveManagersDemo.manager().authenticate(foreign))
            .verifyComplete();
    }

    @Test
    void firstEmptyLetsSecondRun() {
        AtomicInteger secondCalls = new AtomicInteger();

        ReactiveAuthenticationManager empty = auth -> Mono.empty();

        ReactiveAuthenticationManager second = auth -> {
            secondCalls.incrementAndGet();
            return Mono.just(
                UsernamePasswordAuthenticationToken.authenticated(
                    "fallback", null, List.of()));
        };

        var manager = new DelegatingReactiveAuthenticationManager(
            empty, second);

        StepVerifier.create(manager.authenticate(
                passwordRequest("anything")))
            .assertNext(auth ->
                assertEquals("fallback", auth.getName()))
            .verifyComplete();

        assertEquals(1, secondCalls.get());
    }

    @Test
    void firstSuccessStopsLaterManager() {
        AtomicInteger laterCalls = new AtomicInteger();

        ReactiveAuthenticationManager later = auth -> {
            laterCalls.incrementAndGet();
            return Mono.error(
                new IllegalStateException("Must not be invoked"));
        };

        var manager = new DelegatingReactiveAuthenticationManager(
            new ReactiveManagersDemo.ApiKeyManager(), later);

        StepVerifier.create(manager.authenticate(
                apiRequest("demo-service-key")))
            .assertNext(auth -> assertTrue(auth.isAuthenticated()))
            .verifyComplete();

        assertEquals(0, laterCalls.get());
    }

    @Test
    void invalidApiKeyDoesNotFallThroughByDefault() {
        AtomicInteger laterCalls = new AtomicInteger();

        ReactiveAuthenticationManager later = auth -> {
            laterCalls.incrementAndGet();
            return Mono.empty();
        };

        var manager = new DelegatingReactiveAuthenticationManager(
            new ReactiveManagersDemo.ApiKeyManager(), later);

        StepVerifier.create(manager.authenticate(
                apiRequest("wrong-key")))
            .expectError(BadCredentialsException.class)
            .verify();

        assertEquals(0, laterCalls.get());
    }

    @Test
    void explicitContinueOnErrorCanAcceptLaterResult() {
        // INTENTIONALLY illustrates RISK; do not copy as production auth policy.
        AtomicInteger laterCalls = new AtomicInteger();

        ReactiveAuthenticationManager permissive = auth -> {
            laterCalls.incrementAndGet();
            return Mono.just(
                UsernamePasswordAuthenticationToken.authenticated(
                    "fallback-user", null, List.of()));
        };

        var manager = new DelegatingReactiveAuthenticationManager(
            new ReactiveManagersDemo.ApiKeyManager(),
            permissive);

        manager.setContinueOnError(true);

        StepVerifier.create(manager.authenticate(
                apiRequest("wrong-key")))
            .assertNext(auth ->
                assertEquals("fallback-user", auth.getName()))
            .verifyComplete();

        assertEquals(1, laterCalls.get());
    }

    @Test
    void wrongPasswordIsAuthenticationFailure() {
        StepVerifier.create(
            ReactiveManagersDemo.manager().authenticate(
                passwordRequest("incorrect")))
            .expectError(BadCredentialsException.class)
            .verify();
    }

    @Test
    void missingApiKeyIsAuthenticationFailure() {
        StepVerifier.create(
            ReactiveManagersDemo.manager().authenticate(
                apiRequest("")))
            .expectError(BadCredentialsException.class)
            .verify();
    }

    @Test
    void allEmptyMeansNoManagerRecognizedToken() {
        ReactiveAuthenticationManager first = auth -> Mono.empty();
        ReactiveAuthenticationManager second = auth -> Mono.empty();
        var manager = new DelegatingReactiveAuthenticationManager(
            first, second);

        StepVerifier.create(manager.authenticate(
                passwordRequest("ignored")))
            .verifyComplete();
    }
}
~~~

Run:

~~~bash
mvn test
~~~

**Expectation:** 10 tests pass when the project is set up properly and Maven resolves dependencies. This is practice code for learners to run, not a test report executed against a production system.

### Test Invariants

| Test | Meaning |
| --- | --- |
| `apiKeyIsAuthenticatedByFirstManager` | Valid API key returns trusted service principal and `ROLE_SERVICE` |
| `passwordFallsThroughFirstManagerToSecond` | Manager 1 returns empty for password token; manager 2 authenticates |
| `unsupportedTypeReturnsEmptyInsteadOfCastError` | Token outside both protocols causes no `ClassCastException` |
| `firstEmptyLetsSecondRun` | `Mono.empty()` genuinely allows fallback |
| `firstSuccessStopsLaterManager` | A successful result halts iterating through remaining delegates |
| `invalidApiKeyDoesNotFallThroughByDefault` | `Mono.error()` halts fallback by default |
| `explicitContinueOnErrorCanAcceptLaterResult` | Enabling the flag shifts security boundaries; test deliberately demonstrates the risk |
| `wrongPasswordIsAuthenticationFailure` | Wrong password does not become empty |
| `missingApiKeyIsAuthenticationFailure` | Matching token type with missing credential is rejected |
| `allEmptyMeansNoManagerRecognizedToken` | When all delegates abstain, no trusted identity is synthesized |

The `explicitContinueOnErrorCanAcceptLaterResult` test is **not a recommendation to enable `true`**: it clearly shows that an error in the first delegate can be bypassed by a later delegate. Apply fallback-after-error policies only after verifying every condition, credential type, and tenant/issuer boundary.

## 9. Using the Built-In Manager for Username/Password in WebFlux

The CLI exercise wrote `PasswordManager` manually to highlight the `Mono` contract, yet production should not hand-roll full password authentication by default. Spring Security provides `UserDetailsRepositoryReactiveAuthenticationManager`, which uses `ReactiveUserDetailsService` to verify username/password via `PasswordEncoder`.

**Illustrative** configuration snippet, not standalone:

~~~java
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

PasswordEncoder encoder = new BCryptPasswordEncoder();

var users = new MapReactiveUserDetailsService(
    User.withUsername("alice")
        .password(encoder.encode("learn-password"))
        .roles("USER")
        .build()
);

var passwordManager =
    new UserDetailsRepositoryReactiveAuthenticationManager(users);
passwordManager.setPasswordEncoder(encoder);

ReactiveAuthenticationManager manager =
    new DelegatingReactiveAuthenticationManager(
        apiKeyManager, passwordManager);
~~~

Above, `apiKeyManager` is the API key manager created earlier. In a real project, beans and user stores should be dependency-injected and lifecycle-managed by Spring.

**Note:** `MapReactiveUserDetailsService` is suitable only for demos or small scale. Real products should use a trusted repository/IdP ensuring underlying operations are truly reactive or properly offloaded, storing password hashes and account statuses using standard practices.

If integrating a legacy synchronous manager, Spring Security provides `ReactiveAuthenticationManagerAdapter` to wrap `AuthenticationManager`, though you must configure its scheduler and account for blocking. Never call `blockingManager.authenticate(...)` directly on the event-loop.

## 10. Wiring the Manager into AuthenticationWebFilter in WebFlux

At the HTTP layer, `AuthenticationWebFilter` is the WebFlux counterpart in purpose to Servlet authentication filters, operating on `ServerWebExchange` and `Mono`.

Key APIs:

~~~java
AuthenticationWebFilter filter =
    new AuthenticationWebFilter(reactiveManager);

filter.setRequiresAuthenticationMatcher(requestMatcher);
filter.setServerAuthenticationConverter(converter);
filter.setSecurityContextRepository(contextRepository);
filter.setAuthenticationSuccessHandler(successHandler);
filter.setAuthenticationFailureHandler(failureHandler);
~~~

**This is an API template**; `reactiveManager`, `requestMatcher`, `converter`, `contextRepository`, and the handlers must be supplied.

Flow:

1. `setRequiresAuthenticationMatcher` decides whether the filter applies to the request.
2. `ServerAuthenticationConverter.convert(ServerWebExchange)` reads credentials and returns an **unauthenticated** `Mono<Authentication>`, or `Mono.empty()` if no matching login mechanism is present.
3. `AuthenticationWebFilter` sends the token to the composite `ReactiveAuthenticationManager`.
4. On success, the filter stores the result in **`ReactiveSecurityContextHolder`** and invokes the success handler; persistence across requests depends on `ServerSecurityContextRepository`.
5. If authentication fails, the failure handler returns the appropriate status/response.

**Two places returning empty have different meanings:**

~~~text
Converter -> Mono.empty()
    : Does not create Authentication to pass to manager.
      No authentication attempt for that filter.

Manager -> Mono.empty()
    : Authentication exists, but current manager is not
      responsible; DelegatingReactiveAuthenticationManager may try next.
~~~

Do not let a converter read the wrong header and build an unrelated `Authentication`; and do not let a manager read HTTP headers via ThreadLocal or look for `HttpServletRequest` in WebFlux.

## 11. HTTP Configuration Example with One Converter for Two Credential Types

This is an **illustrative integration snippet** for a Spring Boot WebFlux application; it will not compile alongside the CLI `pom.xml` in Section 7 unless web dependencies and Spring configuration classes are added.

Add the appropriate dependencies in a WebFlux application:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
~~~

Do not add `spring-boot-starter-web` to this WebFlux demo unintentionally, because Spring Boot chooses a web application type automatically when both MVC and WebFlux are present.

The configuration assumes `ReactiveManagersDemo` from Section 7 is in the same module/classpath:

~~~java
package demo.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.AuthenticationWebFilter;
import org.springframework.security.web.server.authentication.ServerAuthenticationConverter;
import org.springframework.security.web.server.authentication.ServerHttpBasicAuthenticationConverter;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;
import reactor.core.publisher.Mono;

@Configuration
@EnableWebFluxSecurity
public class ExampleWebFluxSecurity {

    @Bean
    ReactiveAuthenticationManager reactiveManager() {
        return ReactiveManagersDemo.manager();
    }

    @Bean
    SecurityWebFilterChain apiChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager manager) {

        AuthenticationWebFilter filter =
            new AuthenticationWebFilter(manager);

        // Applies only to /api/**.
        filter.setRequiresAuthenticationMatcher(
            ServerWebExchangeMatchers.pathMatchers("/api/**"));

        var basicConverter =
            new ServerHttpBasicAuthenticationConverter();

        ServerAuthenticationConverter converter = exchange -> {
            var headers = exchange.getRequest().getHeaders();
            String apiKey = headers.getFirst("X-API-Key");
            String authorization =
                headers.getFirst("Authorization");

            // Disallow requests specifying both mechanisms simultaneously.
            if (apiKey != null && authorization != null) {
                return Mono.error(new BadCredentialsException(
                    "Ambiguous credentials"));
            }

            if (apiKey != null) {
                return Mono.just(
                    ReactiveManagersDemo.ApiKeyToken.unauthenticated(
                        apiKey));
            }

            // HTTP Basic converter returns UsernamePasswordAuthenticationToken
            // or Mono.empty if Basic header is absent.
            return basicConverter.convert(exchange);
        };

        filter.setServerAuthenticationConverter(converter);

        // Header-based stateless API: do not write an HTTP session.
        filter.setSecurityContextRepository(
            NoOpServerSecurityContextRepository.getInstance());

        filter.setAuthenticationFailureHandler((webFilter, error) -> {
            var response = webFilter.getExchange().getResponse();
            response.setStatusCode(HttpStatus.UNAUTHORIZED);
            return response.setComplete();
        });

        return http
            .securityMatcher(
                ServerWebExchangeMatchers.pathMatchers("/api/**"))
            .authorizeExchange(ex -> ex
                .anyExchange().authenticated())
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .exceptionHandling(ex -> ex.authenticationEntryPoint(
                (exchange, error) -> {
                    var response = exchange.getResponse();
                    response.setStatusCode(HttpStatus.UNAUTHORIZED);
                    return response.setComplete();
                }))
            .addFilterAt(filter, SecurityWebFiltersOrder.AUTHENTICATION)
            .build();
    }
}
~~~

**Configuration breakdown:**

- `AuthenticationWebFilter` is inserted at `SecurityWebFiltersOrder.AUTHENTICATION`.
- `X-API-Key` builds an `ApiKeyToken`, while `Authorization: Basic ...` is converted by the built-in converter into `UsernamePasswordAuthenticationToken`.
- If both credential types are present, the filter returns an error rather than arbitrarily preferring one header, preventing confusion attacks.
- `DelegatingReactiveAuthenticationManager` routes based on the token class without reading HTTP requests directly.
- `NoOpServerSecurityContextRepository` illustrates statelessness: the authentication result applies to **the current request**, without persisting a session for future requests.
- `.httpBasic(...disable())` disables the default Basic filter so it does not process the header before our custom filter; here the Basic converter is invoked from our **custom filter**.
- `.formLogin(...disable())` prevents another login filter from competing for the request.
- Both the failure handler and entry point consistently return 401; auth errors do not leak secrets or account details.

**Limitations:** this snippet targets a WebFlux module with the proper dependencies. The app still needs `/api/**` controllers and a CSRF policy matched to the threat model. If completely stateless and credentials arrive only in headers that browsers do not attach automatically, CSRF policy may differ; **never** disable CSRF unconditionally if the app still uses session cookies or form login in another chain.

### HTTP Call Examples

Once a `GET /api/me` controller requiring authentication exists, the two matching requests are:

~~~bash
curl -i http://localhost:8080/api/me \
  -H 'X-API-Key: demo-service-key'
~~~

~~~bash
curl -i -u alice:learn-password \
  http://localhost:8080/api/me
~~~

When authentication succeeds, the controller sees `service-client`/`ROLE_SERVICE` for the API key request or `alice`/`ROLE_USER` for the Basic request. This is expected behavior **once the controller and WebFlux configuration are built completely**, not output from the CLI-only `pom.xml` in Section 7.

**Warning:** HTTP Basic transmits credentials in Base64 inside a header, not encryption. Use over HTTPS only. API keys are also bearer credentials; store hashes/key IDs on the server, enforce rotation and rate limiting, and never log raw headers.

## 12. When Is ReactiveAuthenticationManagerResolver Better Than Delegating?

`DelegatingReactiveAuthenticationManager` fits when **one token is sent down an ordered list of managers**, each following rules to claim responsibility.

In complex applications, however, choosing a manager sometimes depends on **request context**:

- Multi-tenant apps where each tenant has its own authentication store.
- JWTs coming from multiple authorization servers/issuers.
- Routing by configured host/path or client registration.
- Different API versions/regions requiring distinct policies.
- Certificate or mTLS mechanisms verified by a gateway/ingress.

In those cases, `ReactiveAuthenticationManagerResolver<ServerWebExchange>` lets you select a manager matching the request/issuer context instead of passing every token through all managers.

~~~java
// Illustrates the concept; not a standalone configuration.
ReactiveAuthenticationManagerResolver<ServerWebExchange> resolver =
    exchange -> {
        String path = exchange.getRequest().getPath().value();

        if (path.startsWith("/tenant-a/")) {
            return Mono.just(managerForTenantA);
        }
        if (path.startsWith("/tenant-b/")) {
            return Mono.just(managerForTenantB);
        }
        return Mono.empty();
    };

AuthenticationWebFilter filter =
    new AuthenticationWebFilter(resolver);
~~~

**Security boundary:** client-supplied paths or headers are **not necessarily trusted sources** for tenant/issuer selection. The resolver must use an approved routing mechanism and the selected manager must **independently verify the token, signature, issuer, audience, and tenant**. Specifically, never extract an unverified `iss` claim from a JWT and trust it blindly; any decoder selection must enforce an allowlist and verify signatures/claims against the exact issuer.

### Delegating and Resolvers Are Not Mutually Exclusive

You can use a resolver to select a manager per tenant, and inside each tenant manager use a dedicated delegating manager for API key/username-password. Still, control the number of managers, resource usage, and caching; do not construct an entire new manager chain needlessly on every HTTP request.

## 13. Another Option: Multiple SecurityWebFilterChain Beans

Spring Security WebFlux supports multiple `SecurityWebFilterChain` beans, each with a matcher and order (e.g., `@Order`).

~~~text
/api/partners/** -> chain A: API key
/api/users/**    -> chain B: JWT bearer
/web/**          -> chain C: form login, session/CSRF
~~~

Here, **chain selection** itself bounds which filters and policies apply. If two chains have overlapping matchers, the higher-priority chain can “swallow” requests, bypassing mechanisms meant for the later chain. Always write integration tests covering matchers and ordering.

Choose:
- **DelegatingReactiveAuthenticationManager:** multiple managers can process the same authentication flow with distinct token classes.
- **ReactiveAuthenticationManagerResolver:** select a manager based on exchange/token issuer/tenant context.
- **Multiple SecurityWebFilterChains:** separate entire security policies by path/host, including CSRF, entry points, sessions, and authentication filters.
- **DelegatingServerAuthenticationConverter:** combine multiple ways of extracting credentials from an exchange, **not** a substitute for coordinating managers.

Do not blur these three coordination layers into “a manager finding its own filter.” Each layer handles a distinct responsibility.

## 14. Reactive Does Not Permit Blocking

### For I/O

WebFlux applications handle requests on event-loops; if a manager calls synchronous `jdbcRepository.findBy...` or a blocking HTTP client on the event-loop, throughput and latency collapse.

Depending on the data source:
- R2DBC/reactive repositories: compose `Mono`/`Flux` directly.
- WebClient: use non-blocking HTTP and bound timeouts/retries.
- Systems with only blocking JDBC/SDKs: offload to a suitable scheduler or use `ReactiveAuthenticationManagerAdapter` with an API-configured scheduler; cap concurrent requests.
- BCrypt/Argon2 password hashing: high CPU cost; use an appropriate worker scheduler/resource policy and rate limiting.

### Why Not Use block() Inside authenticate()?

~~~java
// WRONG in a WebFlux request path:
@Override
public Mono<Authentication> authenticate(Authentication authentication) {
    UserRecord user = repository.findById(...).block();
    return Mono.just(toAuthentication(user));
}
~~~

`block()` can throw on non-blocking threads or stall the event-loop. The right way is composition:

~~~java
// Illustrative; repository and toAuthentication are defined by the application.
@Override
public Mono<Authentication> authenticate(Authentication authentication) {
    return reactiveRepository.findUser(authentication.getName())
        .flatMap(user -> verifyCredential(user, authentication))
        .map(this::toAuthentication);
}
~~~

If an irreplaceable blocking call exists, offload it under strict bounds and understand the scheduler. Never use `parallel()` or manual `subscribe()` inside a manager just to pretend blocking is non-blocking; manual subscription breaks context, errors, cancellation, and request control.

### Timeouts and Backend Errors

When an IdP/DB times out, emit an authentication error with **proper semantics and observability**, rather than turning everything into `Mono.empty()` for later managers. `AuthenticationServiceException` fits backend outages better than `BadCredentialsException`; UIs/public APIs can still return a generic message to avoid information leakage.

Unbounded `retryWhen` on the login path can amplify load and credential brute-forcing. Use bounded retries or fail-closed behavior, circuit breakers where appropriate, and test cancellation/timeouts.

## 15. Security: Principal, Authorities, and Trust Boundaries

A manager producing an authenticated `Authentication` must:

1. Actually verify credentials, not merely check the token class.
2. Build the principal from a trusted server/IdP identity, never taking roles from client input.
3. Assign authorities per policy, e.g., `ROLE_SERVICE` for service accounts and `ROLE_USER` for users.
4. Omit raw API keys/passwords from trusted tokens when unnecessary.
5. Check account status, tenant, and issuer/audience for the corresponding token type.
6. Never let a tenant A manager “pass” invalid tokens to tenant B and grant cross-tenant privileges.
7. Ensure `Mono.just(authResult)` is genuinely trusted, never returning the initial unauthenticated object as success.
8. Separate authn from authorization: being authenticated does not grant access to every endpoint.

In WebFlux, the security context follows the **Reactor context**, not simply Servlet's `ThreadLocal` `SecurityContextHolder`. If you call `subscribe()` manually or spawn threads mid-flow, context propagation can break. Let `AuthenticationWebFilter` and the framework manage propagation.

### Logging Rules

Never log:
- `Authorization` headers, API keys, passwords, or bearer tokens.
- Raw `Authentication.getCredentials()`.
- Full signed JWTs or refresh tokens.
- Exception messages containing sensitive backend data.

Log safe metadata such as token type, manager name, outcome, request ID, verified subject, validated tenant/issuer, and duration. When logging “manager A denied”, never include the raw secret.

## 16. Easily Confused Scenarios in Real Projects

### 16.1. Why Isn't Manager 2 Called Even Though Manager 1 Rejected the User?

If manager 1 returns `Mono.error(BadCredentialsException)`, the delegator **stops by default**. That is the expected contract: credentials of that type were handled by manager 1 and determined to be invalid. To fall back due to an **unsupported token**, manager 1 must return `Mono.empty()` *before* verifying credentials it does not own.

### 16.2. Should continueOnError Be Enabled So Users Always Have a Chance to Log In?

Not by default. Rejection due to a locked account, wrong password, or revoked token is an intentional block, not a hint to try a weaker provider. For high availability, handle backend outages at the infrastructure tier or via failover replicas sharing the same authentication policy, rather than random fallback across mechanisms.

### 16.3. Why Does Mono.empty from a Converter Differ from Empty from a Manager?

The converter created no token, so the filter invokes no manager at all. By contrast, a manager's empty happens **after a token exists**, and the delegator may try the next manager. The two steps sit in different layers of responsibility.

### 16.4. What If Multiple Managers Accept UsernamePasswordAuthenticationToken?

Ordering decides who succeeds first. Risks: the same username/password gets interpreted differently across backends, or fallback bypasses one store's account status checks. Separate via token subtypes or pick the manager via a verified resolver/context. Never treat client-supplied `username.endsWith("@tenant")` as proof an identity belongs to that tenant without verification.

### 16.5. Why Not Use Servlet's ProviderManager?

`ProviderManager`/`AuthenticationProvider` are synchronous APIs returning `Authentication`, designed for Servlet. `DelegatingReactiveAuthenticationManager`/`ReactiveAuthenticationManager` return `Mono<Authentication>`. WebFlux filters require reactive interfaces. Reusing legacy synchronous systems requires an adapter/scheduler rather than casting or calling `block()` on Netty threads.

### 16.6. Are There Issues Using a JWT Manager Alongside a Password Manager?

Coexistence itself is not the problem. The danger is that JWTs must have signature, issuer/audience, token type/expiry, and scope validated; you cannot merely parse `sub` or `roles` from the token string and return `Mono.just`. Typically use `oauth2ResourceServer().jwt()` with a standard decoder, or a manager resolver for multiple issuers instead of hand-rolling JWT signature checks.

### 16.7. Can Stateful Form Login and Stateless APIs Coexist?

Yes. However, HTTP sessions/CSRF/cookies and header-based bearer/API keys have different threat models. Use separate `SecurityWebFilterChain` beans when policies differ, or design explicit matchers and repositories within one chain. A `DelegatingReactiveAuthenticationManager` **does not** manage sessions, CSRF, or logout on its own.

### 16.8. What If Every Manager Returns Empty?

That means no manager could produce a result. The delegator does not synthesize an authenticated user. At the HTTP layer, the authentication filter/entry point/authorization rejects per policy—usually 401 when a protected endpoint lacks an identity. Never treat “empty” as success.

### 16.9. Is Mono.just from the First Manager with authenticated=false Okay?

That is a broken design. A `ReactiveAuthenticationManager` is expected to return an authenticated result on success; the manager must verify credentials and construct a trusted result. Do not rely on the delegator to recheck the `authenticated` flag in place of manager logic.

### 16.10. Can a Later Manager's Error Be Ignored Because an Earlier Manager Succeeded?

An earlier manager's success terminates evaluation; later managers need not be invoked. If you run managers concurrently and combine them with `Mono.firstWithSignal`, that has different semantics and can introduce races/bypasses. The delegator is designed to iterate sequentially, not “race” authentication backends.

## 17. Design and Review Checklist

- [ ] Each authentication mechanism has a clear token class; never reuse username/password tokens for API keys or JWTs.
- [ ] Each `ReactiveAuthenticationManager` returns `Mono.empty()` **only** when it cannot handle or decide per contract.
- [ ] Invalid credentials of a supported type must emit `Mono.error(AuthenticationException)`.
- [ ] Managers never return `null` or build trusted principals before verification.
- [ ] `DelegatingReactiveAuthenticationManager` delegate order is explicitly defined and tested.
- [ ] Keep default `setContinueOnError(false)` unless a security review approves a different policy.
- [ ] Tested: first success stops, first empty continues, first error stops, all empty, and fallback if configured.
- [ ] HTTP converters create tokens only when the request carries properly formatted credentials, without “stealing” requests from other filters.
- [ ] `AuthenticationWebFilter` has the right matcher/manager/success-failure handlers for its chain.
- [ ] When tenant/issuer separation is needed, evaluate `ReactiveAuthenticationManagerResolver` or multiple chains.
- [ ] All JWTs/access tokens are verified by maintained decoders/validators with clear issuer/audience and tenant policies.
- [ ] No blocking DB/SDK calls on Netty event-loops; use reactive drivers or bounded adapters/schedulers.
- [ ] Passwords are hashed with an appropriate `PasswordEncoder`, backed by rate limiting/lockout policies and auditing.
- [ ] Authorities are server-determined; credentials never leak into trusted tokens, logs, or HTTP responses.
- [ ] Stateless vs. stateful is explicit; do not expect the delegating manager to save sessions or handle CSRF.
- [ ] Integration tests verify 401/403, header conflicts, missing credentials, expired tokens, and per-chain policies.

## 18. Self-Check Questions

1. Why does `Mono.empty()` from an API key manager have a different meaning from `Mono.error(BadCredentialsException)`?
2. By default, does an error in the first manager allow the second manager to try those credentials?
3. What kind of bypass can `setContinueOnError(true)` cause when two managers support the same token?
4. How do you prevent an API key manager and a password manager from competing over the same `Authentication`?
5. Does `AuthenticationWebFilter` invoke the manager before or after `ServerAuthenticationConverter`?
6. Does a converter returning `Mono.empty()` cause all managers to be called?
7. Why should `block()` never be used on WebFlux's Netty event-loop?
8. Which built-in class does Spring Security provide to authenticate username/password against `ReactiveUserDetailsService`?
9. When is `ReactiveAuthenticationManagerResolver<ServerWebExchange>` better than a delegator?
10. When are multiple `SecurityWebFilterChain` beans better than a single chain with multiple managers?
11. If a JWT has a valid signature but the wrong `aud` or `iss`, should it fall back to the password manager?
12. Why must a result from `Mono.just(auth)` carry a verified principal and authorities?
13. If every manager returns `Mono.empty()`, does the delegator automatically grant an anonymous user?
14. Is using `Mono.firstWithSignal` to pick a manager equivalent to sequential delegation?
15. How do you test that a later manager is not invoked when an earlier manager succeeds or emits an error?

## 19. Official Documentation

1. Spring Security 6.5 — `DelegatingReactiveAuthenticationManager`, constructors, `setContinueOnError`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/DelegatingReactiveAuthenticationManager.html
2. Spring Security 6.5 — `ReactiveAuthenticationManager` interface: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html
3. Spring Security 6.5 — `AuthenticationWebFilter` and convert/authentication steps: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html
4. Spring Security 6.5 — `ServerAuthenticationConverter`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationConverter.html
5. Spring Security 6.5 — WebFlux Security Configuration, multiple chains: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
6. Spring Security 6.5 — `UserDetailsRepositoryReactiveAuthenticationManager`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/UserDetailsRepositoryReactiveAuthenticationManager.html
7. Spring Security 6.5 — `ReactiveAuthenticationManagerAdapter`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ReactiveAuthenticationManagerAdapter.html
8. Spring Security 6.5 — Reactive Resource Server JWT: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
9. Reactor Core — Mono and handling empty/error: https://projectreactor.io/docs/core/release/reference/
10. Reactor Test — StepVerifier: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html

**Key takeaway:** `DelegatingReactiveAuthenticationManager` coordinates **managers in order**, rather than verifying credentials itself. `Mono.empty()` means “I cannot decide; try another mechanism”; `Mono.error()` means “this mechanism rejected or errored” and **does not fall back by default**. Combining distinct token types, semantically accurate error signals, and ordering tests is the foundation for supporting multiple reactive authentication mechanisms without weakening security policy.