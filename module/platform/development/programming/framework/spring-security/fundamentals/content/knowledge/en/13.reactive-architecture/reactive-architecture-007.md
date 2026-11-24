# Distinguishing Empty Publishers, Denial Decisions, and Error Signals in Spring Security Reactive

When working with Spring Security on WebFlux, three outcomes are easily confused: **a Publisher completing without emitting a value**, **a Publisher emitting a decision denying access**, and **a Publisher terminating with an error**. They can lead to similar HTTP outcomes in some situations, yet at the Reactor layer and in each API's contract, they carry distinct meanings. Distinguishing them properly prevents accidentally granting access, masking authentication errors, and misdiagnosing 401/403 status codes.

This lesson focuses on Reactor `Mono`, `ReactiveAuthenticationManager`, `ReactiveAuthorizationManager`, `AuthorizationWebFilter`, and how Spring Security translates decisions into request-processing outcomes. Examples use Java 17+ and illustrate the `check(...)` interface of Spring Security 6.3; newer versions add or prefer `authorize(...)`, but the principles for distinguishing signals remain the same.

## 1. Look at the Signal Before Interpreting Business Meaning

A `Mono<T>` emits at most one value. Three forms to recognize:

~~~text
Mono.empty()                        : subscribe → onComplete
Mono.just(decisionFalse)            : subscribe → onNext(decisionFalse) → onComplete
Mono.error(exception)               : subscribe → onError(exception)
~~~

- **Empty (`empty`)**: no `onNext`, terminates normally with `onComplete`. There is no result object to inspect.
- **Denied (`deny`)**: a **decision value** was emitted, such as `new AuthorizationDecision(false)`. The stream still completes normally; `false` itself is not an `onError` signal.
- **Error (`error`)**: the Publisher emits `onError(Throwable)` and stops. The error may be a technical failure or an intentional security exception; you must examine the exception type and where it originated.

| Representation | `onNext`? | Termination | Direct meaning at the Reactor layer |
| --- | --- | --- | --- |
| `Mono.empty()` | No | `onComplete` | No result emitted |
| `Mono.just(new AuthorizationDecision(true))` | Yes, `isGranted()==true` | `onComplete` | Grant decision emitted |
| `Mono.just(new AuthorizationDecision(false))` | Yes, `isGranted()==false` | `onComplete` | Denial decision emitted |
| `Mono.error(new IllegalStateException(...))` | No | `onError` | Execution failed |
| `Mono.error(new AccessDeniedException(...))` | No | `onError` | Denial represented as an exception |

Key insight: **you cannot look at `Mono.empty()` and conclude “allowed” or “denied” without knowing the contract of the method returning that Mono**. Similarly, error is a *signal type*, while “denial” is a *security meaning*: a denial can start as an `AuthorizationDecision(false)` value and later be translated into an `AccessDeniedException`.

## 2. The Same Empty Publisher Changes Meaning by API

### 2.1. In ReactiveAuthenticationManager: User Not Yet Determined

`ReactiveAuthenticationManager.authenticate(Authentication)` returns `Mono<Authentication>`. By this interface's contract:

| Return value | Interpretation |
| --- | --- |
| `Mono.just(authenticated)` | Authentication succeeded; emit an appropriate `Authentication` object |
| `Mono.empty()` | This manager **cannot determine** whether it can authenticate the input object |
| `Mono.error(new BadCredentialsException(...))` | Authentication **failed**; for example, invalid credentials |

For example, a manager that supports only token type A may return empty when given type B so another manager can handle it, **if** the orchestrating mechanism is configured to continue trying. However, if a username/password is already known to be invalid, returning empty as if it were “unrelated” can hide the failure and create unintended fallthrough paths. For determined authentication failures, emit an appropriate `AuthenticationException`. Never assume “`Mono.empty()` = login succeeded.”

Also distinguish an empty `ReactiveSecurityContextHolder.getContext()` (no security context at the read point) from the result of `authenticate(...)`. Having no context does not mean a resource policy granted access.

### 2.2. In ReactiveAuthorizationManager: Abstain, Deny, or Failure

In the Spring Security 6.3 API, `ReactiveAuthorizationManager<T>.check(Mono<Authentication>, T)` returns `Mono<AuthorizationDecision>`:

- `Mono.just(new AuthorizationDecision(true))`: policy answers **ALLOW**.
- `Mono.just(new AuthorizationDecision(false))`: policy answers **DENY**.
- `Mono.empty()`: policy **makes no decision** (*abstain/no decision*), not a grant decision.
- `Mono.error(cause)`: evaluation did not complete normally; preserve or intentionally handle the error type.

Starting in Spring Security 6.4, the `authorize(...)` API was added to return `AuthorizationResult`; in newer versions, check the exact signature and use the recommended API for that version. Semantically, **no decision** still differs from **a denial decision**.

Not every consumer receiving `Mono<AuthorizationDecision>` handles `empty` the same way. Components coordinating multiple policies may have their own rules for voting, precedence, or default outcome. Always read the contract of the **consuming component**, not just the manager producing the result.

### 2.3. In verify: Completing Empty Can Mean SUCCESS

`ReactiveAuthorizationManager.verify(...)` returns `Mono<Void>`: this method **emits no result object when the check succeeds**. For the default implementation in Spring Security 6.3, both a denial decision and an abstention lead to `AccessDeniedException`; a grant decision leads to normal completion.

~~~text
check(...) → AuthorizationDecision(true)  → verify(...) → onComplete   (allow)
check(...) → AuthorizationDecision(false) → verify(...) → onError(AccessDeniedException)
check(...) → Mono.empty()                 → verify(...) → onError(AccessDeniedException)
check(...) → onError(IllegalStateException) → verify(...) → onError(IllegalStateException)
~~~

This is the easiest place to get confused: **`Mono<Void>` completing empty after `verify` is a successful check**, whereas **`Mono<AuthorizationDecision>` completing empty from `check` means no decision was made**. The return type and processing layer determine the meaning, not just the word “empty.”

A `Mono<Void>` used for `WebFilter.filter` also normally completes without emitting a value when processing succeeds. Do not attach `switchIfEmpty` to a `Mono<Void>` to guess that the pipeline denied access.

## 3. Context in the Spring Security WebFlux Chain

You can think through the processing flow in these conceptual steps (exact ordering depends on the filter chain configuration):

1. **Receive the request and look for credentials.** Authentication filters may extract credentials from Basic, Bearer token, session, or another mechanism. Lacking matching credentials is not yet an `AuthorizationDecision(false)`.
2. **Authenticate identity when matching input exists.** A succeeding `ReactiveAuthenticationManager` supplies an `Authentication`; a determined failure emits an authentication error. `Mono.empty()` here only says that manager could not decide.
3. **Place identity into the reactive context.** Spring Security can supply `SecurityContext` via Reactor `Context`; do not assume it is a `ThreadLocal` variable readable from every thread.
4. **Evaluate access permissions.** `AuthorizationWebFilter` pairs `ReactiveAuthorizationManager` with the request and authentication; the policy can grant or deny.
5. **Handle the decision/error.** Access-denied errors are handled by the corresponding security mechanism; technical errors must not automatically turn into “allowed.”

WebFlux rule example:

~~~java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/public/**").permitAll()
    .pathMatchers("/admin/**").hasRole("ADMIN")
    .anyExchange().authenticated()
)
~~~

`hasRole("ADMIN")` checks the authority `ROLE_ADMIN` under the default convention. An authenticated user without that authority must be denied; an invalid token must be rejected at the authentication step before there is any basis to trust roles claimed by the token. In real applications, prefer built-in rules such as `hasRole`, `authenticated`, and `denyAll` rather than writing custom policies unnecessarily.

### Why Can't Empty/Deny/Error Be Hard-Mapped to HTTP 200/401/403/500?

The HTTP status code is decided after signals pass through filters, exception handlers, authentication entry-point selection, and application configuration:

| Scenario | Typical outcome | Thing to remember |
| --- | --- | --- |
| Unauthenticated, accessing a login-protected path | 401 for HTTP Basic/Bearer, or redirect to login page | Depends on `ServerAuthenticationEntryPoint` and login mechanism |
| Authenticated, lacking permission | 403 | `ServerAccessDeniedHandler` typically handles the response |
| Invalid/expired token | Authentication error response, typically 401 for Bearer | This is an authentication failure, not “abstain” |
| Policy denies via `AuthorizationDecision(false)` | After translation, typically becomes an access-denied error | Do not equate `onNext(false)` with `onError` |
| Policy store or dependent service fails | Technical error propagates or is handled per error policy | Do not blindly tie every error to 403/500 |
| Handler returns `Mono.empty()` after being authorized | May be a response with an empty body | Not a sign that Spring Security denied the request |

In Spring Security WebFlux, `ExceptionTranslationWebFilter` handles `AccessDeniedException` and chooses between initiating authentication or handling denial depending on identity state. Final HTTP values also depend on other settings. Therefore, trace the exception, filters, and policy rather than guessing the outcome from a single `Mono`.

## 4. Configuration Example: Actively Emitting DENY When Identity Is Missing

The following is a complete configuration class for a Spring Boot project using WebFlux and Spring Security. It illustrates distinguishing “no authentication object” from “insufficient permissions,” while returning an **explicit decision** at the check point. File name: `SecurityConfig.java` (add `package` per your project structure).

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authorization.AuthorizationContext;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        ReactiveAuthorizationManager<AuthorizationContext> adminOnly =
                (authentication, context) -> authentication
                        .map(auth -> new AuthorizationDecision(
                                auth.isAuthenticated()
                                        && auth.getAuthorities().stream()
                                        .anyMatch(authority ->
                                                "ROLE_ADMIN".equals(authority.getAuthority()))
                        ))
                        .defaultIfEmpty(new AuthorizationDecision(false));

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public/**").permitAll()
                        .pathMatchers("/admin/**").access(adminOnly)
                        .anyExchange().authenticated()
                )
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

Point-by-point explanation:

- `authentication` is a `Mono<Authentication>`. When present, `map` checks whether the user is authenticated and has `ROLE_ADMIN`; the result is always `AuthorizationDecision(true/false)`.
- If the authentication source is empty, `map` does not run. `defaultIfEmpty(new AuthorizationDecision(false))` supplies a **denial decision**, avoiding letting the policy method accidentally return “no decision.”
- If the authentication source emits an error, `defaultIfEmpty` **does not catch the error**; the error continues propagating. This is the desired behavior when a failure needs to be surfaced.
- `access(adminOnly)` lets you plug a custom policy into `authorizeExchange`. When you only need a role check, `hasRole("ADMIN")` is more concise and should be the standard choice.

This is a policy example, not a complete user/token management solution. To run in a Spring Boot project, you need `spring-boot-starter-webflux` and `spring-boot-starter-security`. If the application uses Spring MVC/Servlet, the corresponding configuration uses a different API family (e.g., `SecurityFilterChain` instead of `SecurityWebFilterChain`).

## 5. Verifying with StepVerifier: Five Isolated Cases

In a Gradle project with Spring Boot 3.3 / Spring Security 6.3, you can include the standard test dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Place `AuthorizationSignalsTest.java` in `src/test/java` (add the matching project `package`). These are unit tests for signals and the `verify` contract, not end-to-end HTTP tests.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.core.Authentication;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertFalse;

class AuthorizationSignalsTest {

    private final Mono<Authentication> noAuthentication = Mono.empty();
    private final Object resource = new Object();

    @Test
    void emptyPublisherHasNoDecision() {
        ReactiveAuthorizationManager<Object> abstain =
                (authentication, target) -> Mono.empty();

        StepVerifier.create(abstain.check(noAuthentication, resource))
                .verifyComplete(); // Neither onNext nor onError
    }

    @Test
    void deniedDecisionIsAValue() {
        Mono<AuthorizationDecision> denied =
                Mono.just(new AuthorizationDecision(false));

        StepVerifier.create(denied)
                .assertNext(decision -> assertFalse(decision.isGranted()))
                .verifyComplete(); // Emits false, completes normally
    }

    @Test
    void technicalErrorIsNotAnEmptyCompletion() {
        Mono<AuthorizationDecision> failed =
                Mono.error(new IllegalStateException("policy store unavailable"));

        StepVerifier.create(failed)
                .expectErrorMatches(error ->
                        error instanceof IllegalStateException
                                && "policy store unavailable".equals(error.getMessage()))
                .verify();
    }

    @Test
    void verifyRejectsBothAbstentionAndDenial() {
        ReactiveAuthorizationManager<Object> abstain =
                (authentication, target) -> Mono.empty();
        ReactiveAuthorizationManager<Object> deny =
                (authentication, target) ->
                        Mono.just(new AuthorizationDecision(false));

        StepVerifier.create(abstain.verify(noAuthentication, resource))
                .expectError(AccessDeniedException.class)
                .verify();

        StepVerifier.create(deny.verify(noAuthentication, resource))
                .expectError(AccessDeniedException.class)
                .verify();
    }

    @Test
    void verifyCompletesNormallyForGrant() {
        ReactiveAuthorizationManager<Object> allow =
                (authentication, target) ->
                        Mono.just(new AuthorizationDecision(true));

        StepVerifier.create(allow.verify(noAuthentication, resource))
                .verifyComplete(); // Successful Mono<Void>, emits no onNext
    }
}
~~~

Run in a project with JUnit Platform enabled:

~~~bash
./gradlew test --tests '*AuthorizationSignalsTest'
~~~

On Windows you can use `gradlew.bat test --tests "*AuthorizationSignalsTest"`. **Expected outcome**: all five tests pass. Note that this is the expected outcome based on Spring Security 6.3 logic and API contracts, not captured stdout from a live execution.

In Spring Security versions using `authorize(...)` instead of `check(...)`, adjust the decision-value assertion to match that version's `AuthorizationResult` signature. Tests should always state their version to avoid mixing old/new interfaces.

## 6. Reading Signals While Debugging

Common Reactor operators have distinct scopes:

| Operator | When it fires | Used for |
| --- | --- | --- |
| `doOnNext(value -> ...)` | On `onNext` | Observing ALLOW/DENY decisions |
| `doOnError(error -> ...)` | On `onError` | Recording errors and exception types |
| `doOnSuccess(value -> ...)` on `Mono` | Mono completes successfully; `value` can be `null` if empty | Distinguishing completion with or without a value |
| `switchIfEmpty(fallback)` | Source completes without emitting a value | Specifying a fallback branch for the empty case |
| `onErrorResume(Type.class, handler)` | Source emits an error matching the type | Recovering from a specific error |
| `materialize()` | Turns signals into inspectable objects | Analyzing `onNext/onComplete/onError` during testing |

Example distinguishing Reactor's two branches:

~~~java
Mono<AuthorizationDecision> decision = lookupDecision();

Mono<AuthorizationDecision> evaluated = decision
        .switchIfEmpty(Mono.just(new AuthorizationDecision(false)))
        .doOnNext(result ->
                System.out.println("granted = " + result.isGranted()))
        .doOnError(error ->
                System.err.println("authorization error: " + error.getClass().getSimpleName()));
~~~

This is an **illustrative integration snippet**, since `lookupDecision()` is an application function you must define. If it returns empty, it prints `granted = false`; if it returns a denial decision, it also prints `granted = false`; if it emits an error, `doOnError` runs and the error keeps propagating. `doOnError` only observes; it does not “swallow” errors.

Note two things in particular:

1. **`switchIfEmpty` does not recover from `onError`**; `onErrorResume` does not handle a source that simply completes empty. Using the wrong operator causes the fallback branch never to execute.
2. **Never use blanket `onErrorResume(error -> Mono.empty())` at a security enforcement point.** It can erase traces of authentication errors, authorization evaluation errors, or policy-store failures. Likewise, never use `defaultIfEmpty(new AuthorizationDecision(true))` just to “keep the system moving.” When the basis for a decision is unavailable, define a fail-safe denial policy or propagate the error cleanly.

For `Mono<Void>`, `doOnNext` receives no value to observe even when the operation succeeds. To tell whether processing completed or errored, observe terminal signals or measure outcomes at the specific API. After calling `verify(...)`, a `switchIfEmpty(...)` will see the Mono complete empty even when **access was granted**.

## 7. Mapping to Real-World Scenarios

**Scenario A — Two authentication mechanisms.** A manager for token type A receives token type B: `Mono.empty()` can represent “this type is unsupported.” Another appropriate manager can try if composed with a corresponding delegation mechanism. However, a token A with a bad signature or a wrong password is a determined failure: use an authentication error, do not pretend it was “undecided.”

**Scenario B — Valid user lacking a role.** A valid `Authentication` is passed to the evaluator; `hasRole("ADMIN")` or an equivalent policy returns a denial decision. This is **DENY**, not a missing result; the authorization enforcement component converts the decision into an access-denied error, typically resulting in 403 when the user is already authenticated.

**Scenario C — Custom policy has no decision.** A `ReactiveAuthorizationManager.check(...)` returns `Mono.empty()` because no policy applies. At the `check` layer, that is *abstain*. When the default `verify` is called, this case is rejected with `AccessDeniedException`. If your application uses a custom policy-combining rule, check how it handles *abstain* before concluding the final outcome.

**Scenario D — Permission lookup service fails.** A dependent call returns `Mono.error(new IllegalStateException(...))`. That is a system error requiring monitoring and handling, not “no result.” Turning all errors into ALLOW or empty completion can cause incorrect access grants.

**Scenario E — Handler returns no body.** A WebFlux method is permitted and returns a `Mono<Void>` that completes normally. This is the right completion signal for an operation that emits no data; never infer that the request was blocked purely from an empty state.

## 8. Common Mistakes and How to Self-Check

- **Confusing values with signals:** `AuthorizationDecision(false)` is an `onNext` carrying a denial value; only when the enforcement layer translates it does it become `onError(AccessDeniedException)`.
- **Confusing the `check` and `verify` layers:** empty in `check` means no decision; empty in `verify` on success is the `Mono<Void>` contract.
- **Swallowing authentication exceptions:** turning `BadCredentialsException` into `Mono.empty()` can let another mechanism keep trying when it should not.
- **Hard-guessing HTTP statuses from a Mono:** 401, 403, redirects, or other error responses depend on filters, exception types, and configuration mechanisms.
- **Missing default policy:** when building custom authorization, explicitly define behavior when identity is absent, permission data is missing, or the policy does not apply.
- **Testing only the ALLOW branch:** test at least empty, deny, error, and the translation through `verify`; for HTTP, add tests for anonymous users, under-privileged users, and authorized users.
- **Using the wrong API version:** Spring Security 6.3's `check(...)` differs from the `authorize(...)` API recommended in newer versions; confirm your actual dependency before copying code.

Ask yourself four questions whenever you see an empty Publisher on a security path: **What type does this Publisher return? What does empty mean according to the contract of the method creating it? Which component consumes it next? At which point and via which exception is the decision turned into an HTTP response?** Answering those four questions separates “undecided,” “denied,” and “errored” without conflating them.

## Reference Documentation

- [ReactiveAuthenticationManager — authentication result contract](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/authentication/ReactiveAuthenticationManager.html)
- [ReactiveAuthorizationManager — 6.3 API, check and verify](https://docs.spring.io/spring-security/site/docs/6.3.0-RC1/api/org/springframework/security/authorization/ReactiveAuthorizationManager.html)
- [Spring Security — WebFlux method authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security — authorize HTTP requests in WebFlux](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Project Reactor — Mono API and signal operators](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
