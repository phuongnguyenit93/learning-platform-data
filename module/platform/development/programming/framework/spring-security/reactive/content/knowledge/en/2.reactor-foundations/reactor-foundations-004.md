# Distinguishing Mono.empty(), false Values, and Error Signals in Security Decisions

## Lesson Objectives

After this lesson, you can: (1) accurately read Reactor signals from `Mono<Boolean>` and `Mono<AuthorizationDecision>`; (2) distinguish "no decision", "deny decision", and "unable to decide due to error"; (3) use Reactor operators to build fail-closed (deny-by-default) policies without hiding failures; (4) test each path independently before integrating with Spring Security WebFlux.

This lesson belongs to **Reactor Foundations** in **Spring Security - reactive**. The focus is the meaning of asynchronous signals at the **authorization** boundary. Authentication (who is the user) provides identity; authorization (is the user allowed to do this) produces the decision for a resource or action.

## 1. Three Termination Outcomes of a `Mono` to Distinguish

`Mono<T>` emits **at most one value**. When it has a value, it emits `onNext(value)` followed by `onComplete()`; when it has no value, it emits only `onComplete()`; on failure, it emits `onError(error)`. These are stream **signals**, not three ways of writing the same result.

| `Mono<Boolean>` source | Observed signal sequence | Meaning at the data layer |
| --- | --- | --- |
| `Mono.just(true)` | `onNext(true) → onComplete` | Has a result; value is `true` |
| `Mono.just(false)` | `onNext(false) → onComplete` | Has a result; value is `false` |
| `Mono.empty()` | `onComplete` | Completed normally without **emitting any value** |
| `Mono.error(new IllegalStateException("unavailable"))` | `onError(IllegalStateException)` | Stream failed; no successful result |

**Key takeaway:** `false` is a **valid value**; `empty` is the **absence of a value**; `error` is **a failure**. `Mono.just(null)` is not a way to represent "no data" (Reactor forbids emitting `null` via `onNext`). Use `Mono.empty()` or a domain type explicitly expressing the reason for absence.

Do not confuse `Mono<Void>` with `Mono<Boolean>`: an empty completion of `Mono<Void>` usually signifies an **operation that succeeded without returning data** (such as finishing a log write). In contrast, an empty `Mono<AuthorizationDecision>` means **no decision object was emitted**. Meaning depends on the **return type and the consumer's contract**.

## 2. Interpretation in Security Decisions

Consider a rule: "Can account A read document D?". If the rule API returns `Mono<Boolean>`, you can establish a clear convention:

| Rule result | Appropriate interpretation | Design action |
| --- | --- | --- |
| `Mono.just(true)` | Rule confirms access is permitted | Represent **ALLOW** |
| `Mono.just(false)` | Rule confirms access is denied | Represent **DENY** |
| `Mono.empty()` | Rule emitted no verdict: record not found, not applicable, or `abstain` depending on contract | **Do not automatically treat as ALLOW**; define fallback rule |
| `Mono.error(cause)` | Rule did not complete due to data, connection, coding, or timeout error… | Preserve the error for proper handling/logging; do not fake `false` or `empty` |

In Spring Security reactive, `ReactiveAuthorizationManager` uses results of type `Mono<AuthorizationDecision>` (and in newer APIs, `Mono<AuthorizationResult>`). An `AuthorizationDecision(true)` and an `AuthorizationDecision(false)` are **two explicit decisions**. The API documentation describes `Mono.empty()` from the decision method as **unable to reach a decision**, commonly called `abstain`. However, what **ultimately** happens to the request depends on how the manager, rule combinator, and filter consume the result; never deduce "empty automatically passes". Methods like `verify(...)` have a different contract: completing `Mono<Void>` when authorization succeeds and emitting an error when denied.

In Spring Security 6.5, `ReactiveAuthorizationManager.check(...)` returns `Mono<AuthorizationDecision>` but has been marked deprecated in favor of `authorize(...)` (introduced in 6.4). For Spring Security 7, follow the `authorize(...)` signature of the version in use. What stays essential across versions is **distinguishing a no-decision signal from a deny decision**.

Business example:

- **Permission record exists with `allowed=false`**: return a **DENY** decision.
- **No permission record exists**: the query layer may return `Mono.empty()`; a "deny if no permission is granted" policy must **intentionally convert empty to DENY**.
- **Permission database loses connection**: emit `onError`; do not turn it into "permission does not exist" without defining an incident-handling policy.

## 3. Reactor Operators That Can Easily Alter Security Meaning

| Operator | When `false` | When `empty` | When `error` |
| --- | --- | --- | --- |
| `map(f)` | Calls `f(false)` | Skips `f`, stays empty | Propagates error |
| `defaultIfEmpty(false)` | Keeps `false` | Emits `false` | Propagates error |
| `switchIfEmpty(fallback)` | Does not run fallback | Runs fallback | Does not run fallback, propagates error |
| `onErrorResume(fallback)` | Keeps `false` | Keeps empty | Runs fallback to handle error |
| `filter(Boolean::booleanValue)` | **Turns into empty** | Stays empty | Propagates error |
| `hasElement()` | Emits `true` because **an element exists** | Emits `false` | Propagates error |

From the table above, four common traps emerge:

1. `defaultIfEmpty(true)` or `switchIfEmpty(Mono.just(true))` turns **missing permission data** into allowing access (**fail-open**). Avoid this configuration for resources that must be protected by default.
2. `filter(Boolean::booleanValue)` or `filterWhen(...)` can strip out the `false` element, leaving only `empty`. Then downstream layers can no longer distinguish "explicitly denied" from "no decision yet".
3. `hasElement()` on `Mono.just(false)` returns `true`. Using it to check "whether allowed" gives the wrong answer: the operator asks **whether an element exists**, not **whether the element's value is true**.
4. `onErrorComplete()` or `onErrorResume(e -> Mono.empty())` can turn an infrastructure error into `abstain`. If a downstream policy combinator accepts empty results, the system may bypass checks. `onErrorReturn(true)` is even more dangerous because it grants access directly on error.

`Mono.zip(permissionA, permissionB)` also requires care: if one branch completes empty without a value, the zip lacks values to build a tuple and can complete empty. If the policy requires two explicit results, normalize **both sources** to `true/false` at the proper data boundary before zipping.

## 4. Designing a Deny-by-Default (Fail-Closed) Rule

Suppose the permission store provides:

```java
// Illustrative snippet: permissionService is provided by the application.
// Not a standalone Java program.
Mono<Boolean> raw = permissionService.canRead(userId, documentId);
```

The contract of `canRead` should be clearly stated: `true` if allowed; `false` if the permission check completed and denied; `empty` if no permission record exists; `error` if the check failed. When applying a "no record means no permission" policy:

```java
Mono<Boolean> allowed = permissionService.canRead(userId, documentId)
        .defaultIfEmpty(false);
```

The result after transformation is **true → true, false → false, empty → false, error → error**. This is an intentional choice: **missing permission data** maps to **deny**; **infrastructure failures** remain errors so handling layers can respond per operational policy and record evidence.

To express the result for Spring Security:

```java
// Snippet for contexts using AuthorizationDecision.
Mono<AuthorizationDecision> decision =
        permissionService.canRead(userId, documentId)
                .map(AuthorizationDecision::new)
                .defaultIfEmpty(new AuthorizationDecision(false));
```

Only treat `empty` as "no record" **when that is the true contract** of the permission store. If the source returns empty meaning "rule does not apply" (abstain) so another rule can decide, do not automatically force it to `false` too early. Define the rule-combining policy, then place **one deny-by-default decision** at the final aggregation point when the business requires it.

If infrastructure failures must be converted to **DENY** instead of letting the error propagate, restrict error catching to the specific recognized exception type, log/audit the failure, and never convert it to **ALLOW**. The example below is only an optional approved policy, not Reactor's default:

```java
Mono<Boolean> allowed = permissionService.canRead(userId, documentId)
        .defaultIfEmpty(false)
        .onErrorResume(PermissionServiceUnavailableException.class, error -> {
            audit.recordPermissionCheckFailure(userId, documentId, error);
            return Mono.just(false);
        });
```

In the snippet above, `PermissionServiceUnavailableException` and `audit` are application-defined components. Converting errors to `false` can change the HTTP status code and hide outages from metrics if recording is omitted. Always weigh the ability to distinguish "forbidden" from "system unable to verify".

## 5. Runnable Java Example: Observing All Four Outcomes on One Pipeline

The following example only requires Reactor Core; it has no Spring Security dependency. It deliberately turns all four states into strings for **diagnostic printing**. The `onErrorResume` branch in this printing program is **not** a permission-granting policy pattern.

Create `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.7.0'
}

application {
    mainClass = 'SecuritySignalsDemo'
}
```

Create `src/main/java/SecuritySignalsDemo.java`:

```java
import reactor.core.publisher.Mono;

public class SecuritySignalsDemo {
    public static void main(String[] args) {
        print("true", Mono.just(true));
        print("false", Mono.just(false));
        print("empty", Mono.empty());
        print("error", Mono.error(
                new IllegalStateException("permission store unavailable")));
    }

    private static void print(String name, Mono<Boolean> source) {
        // Only for observing signals, not for making HTTP decisions.
        String description = source
                .map(allowed -> allowed ? "ALLOW" : "DENY")
                .switchIfEmpty(Mono.just("ABSTAIN"))
                .onErrorResume(error ->
                        Mono.just("ERROR:" + error.getClass().getSimpleName()))
                .block();

        System.out.println(name + " -> " + description);
    }
}
```

Run from the project directory with `gradle run --quiet` (or `./gradlew run --quiet` when a Gradle Wrapper is present). With JDK 17+ and dependencies downloaded successfully, stdout is:

```text
true -> ALLOW
false -> DENY
empty -> ABSTAIN
error -> ERROR:IllegalStateException
```

**Explanation:** `map` runs for both `true` and `false` because both emit `onNext`; `switchIfEmpty` activates only on `empty`; `onErrorResume` handles only `error`. `block()` appears only in this standalone `main` example to observe output; **do not use `block()` in a WebFlux request flow** because it can block reactive processing threads.

Try replacing `.switchIfEmpty(Mono.just("ABSTAIN"))` with `.defaultIfEmpty("DENY")` to see the empty case converted to deny while the error still reaches `onErrorResume`.

## 6. Integrating with ReactiveAuthorizationManager

In Spring Security WebFlux, a `ReactiveAuthorizationManager<AuthorizationContext>` can inspect `Authentication` and request information to emit a decision. The snippet below illustrates the **`check(...)` signature from Spring Security 6.5**, which is deprecated in that version; newer releases move to `authorize(...)` and `AuthorizationResult`. This is an **integration fragment**, requiring Spring Security WebFlux dependencies and the application's `PermissionService`:

```java
import org.springframework.security.authentication.*;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import reactor.core.publisher.Mono;

final class DocumentReadManager
        implements ReactiveAuthorizationManager<AuthorizationContext> {

    private final PermissionService permissions;

    DocumentReadManager(PermissionService permissions) {
        this.permissions = permissions;
    }

    @Override
    public Mono<AuthorizationDecision> check(
            Mono<Authentication> authentication, AuthorizationContext context) {

        String path = context.getExchange().getRequest().getPath().value();

        return authentication
                .flatMap(auth -> permissions.canRead(auth.getName(), path))
                .map(AuthorizationDecision::new)
                .defaultIfEmpty(new AuthorizationDecision(false));
    }
}

// Example contract: no permission record -> Mono.empty();
// permission store failure -> Mono.error(...); record present -> Mono.just(true/false).
interface PermissionService {
    Mono<Boolean> canRead(String principalName, String resourcePath);
}
```

Execution flow:

1. `authentication` emits an `Authentication` → queries permissions, emits `AuthorizationDecision(true/false)` if a result is returned.
2. `authentication` emits no value, or the permission store completes `empty` → `defaultIfEmpty` produces `AuthorizationDecision(false)`.
3. The permission store emits an error → `flatMap` and `map` do not turn it into a decision; the error propagates to the application/framework error-handling layer.

Note that `Authentication` can represent an anonymous user depending on the filter chain. Do not merely check `isAuthenticated()` and assume a genuinely logged-in user: the application must enforce appropriate authentication/anonymous rules. The code above protects by requiring the permission store to return an **explicit grant decision**. Without proof of granted access, it denies.

**HTTP 401, 403, and server errors are a separate processing step:** `Mono.just(false)` here does not itself build a 403 response; Spring Security translates the deny decision into the access-denied handling flow, and the filter/entry point determines the response. Depending on authentication state and configuration, an unauthenticated request may trigger 401 or a login mechanism; an authenticated user lacking permissions typically receives 403. `Mono.error(...)` from a disconnected permission store does not automatically carry the same meaning as `AccessDeniedException`; without dedicated handling, it may become a 5xx error. Therefore, do not conflate **Reactor signals**, **policy decisions**, and **HTTP status codes**.

## 7. Three Real-World Scenarios and How to Decide

**Scenario A — not yet granted permission.** The database returns no ACL row for `(user, document)`. If the API returns `Mono.empty()`, the rule specifies `defaultIfEmpty(false)` at the permission-store boundary. The final outcome is **DENY**; a missing permission row does not become access.

**Scenario B — ACL has row `allow=false`.** The API returns `Mono.just(false)`. The rule records an **explicit denial**; `switchIfEmpty` does not run. If the code used `filter(Boolean::booleanValue)` before auditing, `false` could turn into empty, losing the "explicitly denied" information.

**Scenario C — ACL service times out.** The API returns `Mono.error(TimeoutException)`. `defaultIfEmpty(false)` **does not** catch this error. Error reporting/monitoring receives the cause, while whether to return 5xx or explicitly deny per resilience policy must be defined. Do not use `onErrorReturn(true)`. Only convert errors to `false` when it is a deliberate policy, while ensuring instrumentation and impact checks.

A fourth, very different scenario: **rule not applicable**. For example, one manager only evaluates resources in the "document" group, while other resource groups are handled by another manager. If the combining contract accepts `abstain`, the manager can return `Mono.empty()` to defer the decision. When no manager grants permission, a final blocking fallback rule is needed; never grant access merely because none emitted a decision.

## 8. Test Each Signal Path, Not Only Status Codes

With `reactor-test` (add `testImplementation 'io.projectreactor:reactor-test:3.7.0'` for the Gradle example above), `StepVerifier` verifies exact underlying signals:

```java
// Snippet used in a JUnit/StepVerifier test; requires importing Mono, StepVerifier.
StepVerifier.create(Mono.just(false))
        .expectNext(false)
        .verifyComplete(); // Has value false.

StepVerifier.create(Mono.<Boolean>empty())
        .verifyComplete(); // No onNext.

StepVerifier.create(
        Mono.<Boolean>error(new IllegalStateException("ACL down")))
        .expectError(IllegalStateException.class)
        .verify(); // Has onError, not empty.

StepVerifier.create(
        Mono.<Boolean>empty().defaultIfEmpty(false))
        .expectNext(false)
        .verifyComplete(); // Fallback rule converted empty to deny.
```

In WebFlux integration tests, design at least four cases: permitted, explicitly denied, no permission record, and failing permission service. Verify **the decision path, side effects, and HTTP response** separately; use `WebTestClient` with the real security chain rather than guessing HTTP codes from an isolated `Mono`. When multiple managers exist, add cases for **all abstain** and **one manager abstains while another denies/allows** according to the defined combining rule.

## 9. Common Mistakes

- **Reading `false` as `empty`:** `switchIfEmpty` does not run when `Mono.just(false)` emits a value. Write tests for both.
- **Using `hasElement()` to grant access:** `Mono.just(false).hasElement()` emits `true` because an element exists. To know the Boolean value, inspect the value itself.
- **Using `filter(Boolean::booleanValue)` too early:** it strips out deny decisions, causing errors in fallback/audit layers.
- **Allowing by default on missing data:** `defaultIfEmpty(true)` can create a vulnerability when the permission store lacks the required row.
- **Swallowing errors with `onErrorComplete()`:** errors are turned into empty signals; subsequent access depends on a potentially unsafe fallback.
- **Converting every error to 403:** hides connection failures, service outages, or bugs; operations cannot tell why access failed.
- **Equating `Mono<Void>` with an empty authorization result:** the two API types carry different contracts.
- **Believing HTTP 401/403 is inferred directly from `Mono`:** filters, exception handlers, anonymous authentication, and configuration decide the final HTTP response.
- **Calling `block()` in a reactive request:** breaks non-blocking behavior and can stall the processing thread.

## 10. Memory Rules and Self-Check Questions

When reading an authorization check flow, ask in order:

1. **What type does the Publisher return?** `Mono<Boolean>`, `Mono<AuthorizationDecision>`, or `Mono<Void>`?
2. **Does it emit `onNext`?** If so, is the value `true` or `false`? If not, is it an empty `onComplete` or `onError`?
3. **What does `empty` mean per the source contract?** Missing data, abstain, or task completed without a return value?
4. **Which operators alter the signal?** Do `filter`, `defaultIfEmpty`, `switchIfEmpty`, `onErrorResume`, or `zip` erase the distinction?
5. **Who makes the final decision?** The rule, a combining manager, a Spring Security filter, or an HTTP exception handler?
6. **Have all four paths been tested?** Allow, deny, empty, and error.

**Self-check:** For `Mono.just(false).switchIfEmpty(Mono.just(true))`, what is the result? **`false`**, because the publisher already has an element. For `Mono.<Boolean>empty().defaultIfEmpty(false)`? **`false`** due to fallback. For `Mono.<Boolean>error(new IllegalStateException()).defaultIfEmpty(false)`? **`onError(IllegalStateException)`**, because an error is not an empty completion signal.

**Final takeaway:** `false` = **explicit deny decision**; `empty` = **no value/decision emitted**; `error` = **unable to complete the check**. A safe security system needs clear contracts for each state, an appropriate deny-by-default decision point, and independent testing of the error path.

## References

- [Project Reactor — Mono, an Asynchronous 0–1 Result](https://projectreactor.io/docs/core/release/reference/coreFeatures/mono.html) — the `onNext`, `onComplete`, `onError` model.
- [Spring Security 6.5 — ReactiveAuthorizationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html) — `check`, `authorize`, `verify`, and the concept of no decision.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html) — custom reactive authorization, `Mono<Boolean>`, and `abstain`.
- [Reactor Core — Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html) — semantics of operators that alter signal paths.
