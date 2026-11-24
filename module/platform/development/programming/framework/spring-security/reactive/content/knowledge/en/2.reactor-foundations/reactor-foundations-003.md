# Chaining `map`, `flatMap`, `filter`, and `switchIfEmpty` in Authentication Flows

## 1. Problem Statement and Goals

In Spring WebFlux applications using Spring Security reactive, authentication is typically a chain of asynchronous steps: read credentials → validate format → look up or verify credentials → evaluate account/token status → build the authenticated user object. Project Reactor lets you express this flow using operators on `Mono<T>` without blocking the request-processing thread.

After this lesson, you should be able to distinguish:
- `map`: **synchronously** transform an existing value.
- `flatMap`: invoke a step producing a new `Mono` (typically asynchronous I/O) and flatten/chain its result into the sequence.
- `filter`: let a value pass only when a synchronous condition is true; if false, complete **empty**.
- `switchIfEmpty`: switch to a fallback `Mono` when the preceding chain completes **without emitting a value**.

The most critical point in authentication: **empty, error, and success are three distinct signals**. Never treat `Mono.empty()` as authenticated success, nor treat all errors as empty.

## 2. Understanding Signals Before Chaining Operators

`Mono<T>` emits at most one element: `onNext(value)` then `onComplete`, or only `onComplete` (empty), or `onError(error)`. Example:

~~~java
Mono.just("linh");                            // Has a value.
Mono.<String>empty();                         // No value, no error.
Mono.<String>error(new IllegalStateException("Failed")); // Has an error.
~~~

A typical `Mono` is *cold*: assembling the chain does not mean running the query. The chain executes when subscribed; in Spring WebFlux, the framework handles subscribing. If the source is empty, downstream `map`, `flatMap`, and `filter` lambdas **are not invoked**; `switchIfEmpty` can provide an alternative branch. If the source errors, the error propagates to subsequent operators and `switchIfEmpty` **does not** catch that error.

| Signal | Meaning in authentication example | Behavior of `switchIfEmpty` |
| --- | --- | --- |
| Has value | Token/claims/user obtained | Does not run fallback branch |
| Completed empty | No data yet, rejected by `filter`, or lookup not found | Runs fallback branch |
| `onError` | Authentication failed, service error, or operator emitted error | Does not run; error keeps propagating |

When composing steps, ask yourself: "Does this step return a value, a `Mono`, or can it return empty/error?"

## 3. Exact Roles of the Four Operators

### 3.1. `map` — synchronous data transformation

Signature: `Mono<T>.map(T -> R)` produces `Mono<R>`.

~~~java
Mono<String> raw = Mono.just("  Bearer demo-token  ");
Mono<String> normalized = raw.map(String::trim);
~~~

`map` is suitable for trimming whitespace, extracting username/subject from **already-verified** claims, building a DTO, or converting validated claims into a principal. The mapping function must return a non-`null` value. Exceptions thrown inside the function are turned into an `onError` signal.

Do not use `map` to invoke a service returning `Mono<User>`:

~~~java
Mono<Mono<User>> nested = usernameMono.map(userRepository::findByUsername);
~~~

The snippet above creates `Mono<Mono<User>>` rather than directly yielding `User`. When the next step must await a result from a reactive repository/API, use `flatMap`.

### 3.2. `flatMap` — chaining asynchronous operations

Signature: `Mono<T>.flatMap(T -> Mono<R>)` produces `Mono<R>`.

~~~java
Mono<User> user = usernameMono.flatMap(userRepository::findByUsername);
~~~

`flatMap` subscribes to the `Mono` returned by the function and forwards its result, error, or emptiness. Typical authentication cases: querying a user via a reactive repository, verifying a token via an asynchronous API, loading permissions from another service. Do not `block()` inside `flatMap`; doing so forfeits non-blocking benefits and can throw errors on WebFlux threads.

For `Mono`, `flatMap` handles at most one value. When the source is a multi-value `Flux`, `flatMap` can interleave inner tasks out of order; that is a separate concern for multi-element streams and need not be mechanically applied to a single-request authentication chain.

### 3.3. `filter` — keeping or dropping a value

Signature: `Mono<T>.filter(T -> boolean)` retains type `Mono<T>`.

~~~java
Mono<String> token = Mono.just("demo-token")
    .filter(value -> !value.isBlank());
~~~

If the predicate returns `false`, the element is dropped and the chain completes empty; `filter` **does not automatically produce an "invalid token" error**. Therefore, an empty-handling branch is needed at a semantically clear point.

`filter` suits synchronous rules: non-blank token, enabled account, claims not marked revoked (if status is already on the object). If evaluating the condition requires calling an API returning `Mono<Boolean>`, use `filterWhen` or `flatMap` with an explicit decision; do not call `block()` inside the predicate.

### 3.4. `switchIfEmpty` — handling the no-result branch

Signature: `Mono<T>.switchIfEmpty(Mono<? extends T>)`.

~~~java
Mono<User> user = userRepository.findByUsername(username)
    .switchIfEmpty(Mono.error(
        new IllegalArgumentException("User not found")));
~~~

This branch only runs when the preceding publisher completes empty. It can be used to emit an error, query a secondary source, or return a default value **if using a default is safe**. For authentication, strictly avoid returning a "default logged-in principal" as a fallback.

To defer *creating* the fallback publisher as well (e.g., a publisher-building function with side effects), use:

~~~java
Mono<User> result = primaryLookup(username)
    .switchIfEmpty(Mono.defer(() -> secondaryLookup(username)));
~~~

`Mono.defer` creates the secondary publisher only when the fallback branch is subscribed to; it also avoids side effects during assembly before fallback is needed. `switchIfEmpty` does not replace `onErrorResume`: authentication errors must be emitted or handled explicitly per policy, never silently turned into a valid user.

## 4. Designing an Authentication Chain in Logical Order

Consider the HTTP input `Authorization: Bearer <token>`. For a valid identifying token, an illustrative flow looks like:

~~~text
Header that may be null
  │
  ▼
Mono.justOrEmpty(header)
  │ map(trim)                  Synchronous normalization
  ▼
filter(startsWith("Bearer ")) Structure check
  │ map(remove prefix)        Extract token
  ▼
filter(token not blank)
  │ switchIfEmpty(error)      Missing token / invalid format → error
  ▼
flatMap(lookupOrVerifyToken)  Lookup/verify returning Mono<Claims>
  │ filter(claims.active)     Drop claims that are no longer active
  ▼
switchIfEmpty(error)          Not found / no longer active → error
  │ map(toPrincipal)          Create authenticated result
  ▼
Mono<Principal> or onError
~~~

Placing `switchIfEmpty` **immediately after the input-validation group** helps distinguish "missing token" from "token supplied but invalid". Placing the second fallback after lookup helps distinguish not found or inactive status. When both branches end with the same error type, the logic can be merged, though at the cost of losing testability separation.

## 5. Runnable Java 17+ Example with Reactor

The example below simulates token lookup with an in-memory `Map` to observe signals. **This is not a production JWT or password verification mechanism**; a real service must verify signatures, expiration, issuer/audience, revocation status, and applicable constraints before accepting an identity.

Create a minimal Gradle application with `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.8'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.ReactiveAuthDemo'
}
~~~

Create `src/main/java/demo/ReactiveAuthDemo.java`:

~~~java
package demo;

import java.util.Map;
import reactor.core.publisher.Mono;

public class ReactiveAuthDemo {

    record TokenClaims(String subject, boolean active) {}
    record Principal(String username, String authority) {}

    private static final Map<String, TokenClaims> TOKENS = Map.of(
        "valid-token", new TokenClaims("linh", true),
        "disabled-token", new TokenClaims("linh", false)
    );

    private static Mono<TokenClaims> lookupToken(String token) {
        // Simulate reactive source: not found => Mono.empty().
        return Mono.defer(() -> Mono.justOrEmpty(TOKENS.get(token)));
    }

    static Mono<Principal> authenticate(String authorization) {
        return Mono.justOrEmpty(authorization)
            .map(String::trim)
            .filter(header -> header.startsWith("Bearer "))
            .map(header -> header.substring("Bearer ".length()).trim())
            .filter(token -> !token.isBlank())
            .switchIfEmpty(Mono.error(
                new IllegalArgumentException("Missing Bearer token")))
            .flatMap(ReactiveAuthDemo::lookupToken)
            .filter(TokenClaims::active)
            .switchIfEmpty(Mono.error(
                new IllegalArgumentException("Invalid or inactive token")))
            .map(claims -> new Principal(claims.subject(), "ROLE_USER"));
    }

    private static void show(String header) {
        try {
            // block() is only used in demo main, NEVER inside a WebFlux handler.
            Principal principal = authenticate(header).block();
            System.out.println("OK: " + principal.username()
                + " (" + principal.authority() + ")");
        } catch (IllegalArgumentException ex) {
            System.out.println("FAIL: " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        show("Bearer valid-token");
        show("Bearer disabled-token");
        show("Bearer unknown-token");
        show(null);
    }
}
~~~

Run from the project directory with `gradle run --quiet` (requires Gradle, JDK 17, and access to download dependencies from Maven Central). If the project has a Gradle Wrapper, use `./gradlew run --quiet` on Unix/macOS or `gradlew.bat run --quiet` on Windows.

Stdout output:

~~~text
OK: linh (ROLE_USER)
FAIL: Invalid or inactive token
FAIL: Invalid or inactive token
FAIL: Missing Bearer token
~~~

**Case-by-case explanation:**
1. `valid-token` → `map` extracts the string, `flatMap` finds active claims, `filter` keeps them, `map` creates `Principal`.
2. `disabled-token` → lookup finds claims, but `filter(TokenClaims::active)` returns false → empty → fallback error "Invalid or inactive token".
3. `unknown-token` → `lookupToken` completes empty → `flatMap` emits empty → same fallback error.
4. `null` → `Mono.justOrEmpty` is empty from the start; `map`/`filter`/`flatMap` before the fallback are never called → error "Missing Bearer token".

Note: using `Mono.defer` here demonstrates creating a publisher per subscription; it **does not** turn a `Map` lookup into asynchronous I/O. In a real application, a reactive repository or client provides a non-blocking publisher.

## 6. Connection to Spring Security Reactive

In WebFlux, `ReactiveAuthenticationManager.authenticate(Authentication)` returns `Mono<Authentication>`. The interface contract carries important meaning:
- Emit an `Authentication` when authentication succeeds.
- Complete empty when the manager **cannot make a decision** for that request (for example, an unsupported authentication type).
- Emit `onError` with an authentication error when credentials were processed and determined to be invalid.

The following example **is only an illustrative integration snippet**, assuming the application already has a `TokenVerifier` returning `Mono<VerifiedClaims>` after full token checks and Spring Security WebFlux/Resource Server configured:

~~~java
import java.util.List;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthenticationToken;
import reactor.core.publisher.Mono;

record VerifiedClaims(String subject, boolean active) {}

interface TokenVerifier {
    // Only return claims after the token has passed security checks.
    Mono<VerifiedClaims> verify(String rawToken);
}

final class CustomReactiveAuthenticationManager
        implements ReactiveAuthenticationManager {

    private final TokenVerifier verifier;

    CustomReactiveAuthenticationManager(TokenVerifier verifier) {
        this.verifier = verifier;
    }

    @Override
    public Mono<Authentication> authenticate(Authentication incoming) {
        if (!(incoming instanceof BearerTokenAuthenticationToken bearer)) {
            return Mono.empty(); // This manager does not handle other token types.
        }

        return verifier.verify(bearer.getToken())
            .filter(VerifiedClaims::active)
            .switchIfEmpty(Mono.error(
                new BadCredentialsException("Invalid credentials")))
            .map(claims -> (Authentication)
                new UsernamePasswordAuthenticationToken(
                    claims.subject(),
                    null,
                    List.of(new SimpleGrantedAuthority("ROLE_USER"))));
    }
}
~~~

Points to read carefully:
- `verifier.verify(...)` is an asynchronous step already returning a `Mono`; in variants that first read a token from a reactive source, use `flatMap(verifier::verify)` to chain it. Do not use `map` to produce `Mono<Mono<VerifiedClaims>>`.
- `filter(VerifiedClaims::active)` accepts only verified and currently active claims.
- `switchIfEmpty` turns "supported token type that could not be verified" into `BadCredentialsException`. Conversely, `Mono.empty()` in the unsupported input type branch means "this manager cannot decide", matching the interface contract.
- `map` turns valid claims into an `Authentication` with authorities. In real systems, assign only authorities reliably derived from policy/claims; `ROLE_USER` here is a demo role, not a real permission-granting rule.

Spring Security already provides built-in JWT and opaque-token decoders/verifiers for Resource Server. Use the built-in capabilities when appropriate; the custom example above is for understanding operator chaining, not a recommendation to hand-roll cryptographic mechanisms.

**Authentication differs from authorization:** authentication proves *who* is accessing; authorization decides *what* that identity is allowed to do. HTTP 401/403 outcomes depend on the configured `SecurityWebFilterChain`, entry point, and access-denied handler; `switchIfEmpty` itself does not emit HTTP statuses. For WebFlux, security context is propagated through Reactor Context (e.g., `ReactiveSecurityContextHolder`), rather than relying on `ThreadLocal` as in standard Servlet flows.

## 7. Distinguishing Empty and Error Branches

A chain prone to logic bugs:

~~~java
Mono<VerifiedClaims> claims = verifier.verify(rawToken)
    .filter(VerifiedClaims::active);
~~~

If `verifier.verify` returns empty when no token is found, `filter` can also return empty when the token is inactive. Without a fallback, downstream may receive an empty completion without an explicit authentication answer. Define each step's contract and add appropriate error handling:

~~~java
Mono<VerifiedClaims> claims = verifier.verify(rawToken)
    .filter(VerifiedClaims::active)
    .switchIfEmpty(Mono.error(
        new BadCredentialsException("Invalid credentials")));
~~~

If `verify` emits an error (such as invalid signature represented by `AuthenticationException`), `switchIfEmpty` neither catches the error nor turns it into a value. Technical errors such as timeouts or database unavailability should be monitored/handled per system policy, never automatically granting login.

Sometimes a fallback is needed when a lookup source lacks data (e.g., cache miss → database). In that case:

~~~java
Mono<VerifiedClaims> claims = cache.find(rawToken)
    .switchIfEmpty(Mono.defer(() -> database.find(rawToken)))
    .filter(VerifiedClaims::active)
    .switchIfEmpty(Mono.error(
        new BadCredentialsException("Invalid credentials")));
~~~

Only use the cache/database pattern above if the returned data has already been validated and the cache cannot be exploited to bypass token verification. Do not choose a lower-trust secondary source to bypass verification failures from the primary source.

## 8. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `map(service::findUser)` when service returns `Mono<User>` | Creates `Mono<Mono<User>>` | `flatMap(service::findUser)` |
| Using `filter` and assuming empty means valid | Can bypass authentication checks | Place `switchIfEmpty(Mono.error(...))` in the right spot |
| Thinking `switchIfEmpty` catches `onError` | Errors still propagate downstream | Separate error and empty; only use `onErrorResume` with an explicit policy |
| Calling `block()` / `subscribe()` in a WebFlux handler | Blocks threads or detaches processing from request lifecycle | Return `Mono` directly to the framework |
| Mapping to `null` inside `map` | Reactor rejects `null` values | Use `Mono.justOrEmpty` / `mapNotNull` intentionally |
| Logging raw passwords/tokens | Leaks authentication secrets | Log only error codes, correlation IDs, and safe metadata |
| `switchIfEmpty(Mono.just(authenticatedFallback))` | Can create a spoofed login | Authentication fallback must follow policy; usually an error |
| Using `filter` with a blocking database call | Blocks the event loop | Use a reactive repository/client with `flatMap` or `filterWhen` |

For synchronous steps, choose `map` or `filter`. For calls returning a publisher, choose `flatMap`. For *no-element* cases, choose `switchIfEmpty` once the meaning of empty is defined. For authentication errors, use error signals and Spring Security's error handling at the proper layer.

## 9. Self-Check Knowledge

1. If a repository returns `Mono.empty()`, does `map(User::getUsername)` run? **No**; there is no `onNext` to map.
2. Does `filter(claim -> false)` throw `BadCredentialsException`? **No**; it produces an empty result. To emit an error, add `switchIfEmpty(Mono.error(...))`.
3. Why can `map(tokenService::verify)` be wrong? Because `verify` returns `Mono<Claims>`, so `map` creates a nested publisher; `flatMap` flattens the result.
4. If `verify` returns `Mono.error(...)`, does `switchIfEmpty` run? **No**; that is an error, not empty.
5. In `ReactiveAuthenticationManager`, does `Mono.empty()` always mean wrong password? **No**; per the interface contract, the manager could not determine a result. Invalid credentials for a supported token type should emit an authentication error.
6. Should you call `.block()` in a WebFlux handler to obtain the principal? **No**; keep the publisher intact and let the framework subscribe.

## Official Documentation

- Project Reactor, `Mono` API: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Spring Security, `ReactiveAuthenticationManager`: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/authentication/ReactiveAuthenticationManager.html
- Spring Security, reactive methods and Reactor Context: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
