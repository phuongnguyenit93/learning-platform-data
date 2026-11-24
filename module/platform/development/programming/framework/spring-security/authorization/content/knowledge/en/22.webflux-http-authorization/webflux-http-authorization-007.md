# Combining Decisions with Reactor Operators Without Unintended Grants

## 1. Context: combining multiple rules in WebFlux HTTP

In Spring Security WebFlux, an endpoint may require several conditions to hold simultaneously before returning a document:

- The caller is authenticated and has authority `DOC_READ`.
- The caller is permitted to operate in the document's tenant.
- The caller is the owner **or** has a valid READ share.
- The document is not locked.
- An external PDP, if configured as a mandatory guard, returns a valid PERMIT.

In synchronous code, you might see a Boolean expression:

```java
boolean allowed =
        hasReadAuthority
        && tenantAllowed
        && (ownerAllowed || shareAllowed)
        && !documentLocked
        && remotePolicyPermitted;
```

In WebFlux, each condition may be evaluated asynchronously via `Mono<Boolean>` or `Mono<AuthorizationResult>`. Translating the expression above into chains of `zip`, `flatMap`, `filter`, `switchIfEmpty`, `all`, `any`, and `onErrorResume` is **not merely a syntax change**: Reactor distinguishes emitted values, empty completion, and errors. Writing it carelessly can turn **no decision** into **granted**.

This lesson focuses on combining decisions in WebFlux HTTP, using `ReactiveAuthorizationManager` properly, normalizing branches into explicit decisions, distinguishing AND/OR, and avoiding dangerous fallbacks. Java 17 snippets are labeled as either **runnable Maven programs** or **Spring Security integration snippets**.

### Learning outcomes

1. Understand how `Mono.just(true)`, `Mono.just(false)`, `Mono.empty()`, and `Mono.error(...)` differ.
2. Know when to use `zip`, `flatMap`, `Flux.all`, and `Flux.any` for mandatory versus alternative permissions.
3. Know to avoid `filter(...).switchIfEmpty(permit)`, `thenReturn(true)`, and `hasElement()`.
4. Never let an empty/error/timeout/abstain branch open access.
5. Know how to wire the logic into `ServerHttpSecurity.authorizeExchange(...).access(...)`.
6. Know how to test combinations with `StepVerifier` and verify the WebFlux filter chain.
7. Preserve tenant, caller, resource, action, and context across scheduler/subscription hops.

## 2. Four `Mono` signals to distinguish

`Mono<T>` emits **at most one value**, completes empty, or terminates with an error. For Boolean decisions:

| Publisher | Signal | Recommended meaning in authorization |
| --- | --- | --- |
| `Mono.just(true)` | `onNext(true)` then `onComplete` | This condition grants access |
| `Mono.just(false)` | `onNext(false)` then `onComplete` | This condition denies access |
| `Mono.empty()` | `onComplete` only | No decision / missing required data |
| `Mono.error(ex)` | `onError(ex)` | Unable to evaluate or infrastructure error |
| `Mono.never()` | No terminal signal | Can hang unless bounded by a timeout |

**No `onNext` is different from `onNext(false)`.** This is a core rule of Reactive Streams. Spring Security's `ReactiveAuthorizationManager.authorize(...)` can return a decision or `Mono.empty()` when the manager abstains; therefore, empty must never be arbitrarily treated as GRANT.

Example:

```java
Mono<Boolean> permit = Mono.just(true);
Mono<Boolean> deny = Mono.just(false);
Mono<Boolean> undecided = Mono.empty();
Mono<Boolean> failed = Mono.error(
        new IllegalStateException("Policy service unavailable"));
```

`null` is not a valid value for `Mono.just(null)`; `Mono` does not emit `null` per Reactive Streams. Do not use a nullable `Boolean` as a third state inside a publisher. If you need to distinguish deny, abstain, and operational failure, use an explicit domain type such as an enum/record instead of collapsing everything to `Boolean` too early.

### Decisions in Spring Security

In Spring Security 6.5, `ReactiveAuthorizationManager<T>` defines:

```java
Mono<AuthorizationResult> authorize(
        Mono<Authentication> authentication, T object);
```

The 6.5 interface still contains `check(...)` returning `Mono<AuthorizationDecision>`, marked deprecated in favor of `authorize(...)`. Some classes or libraries may still use `check`; when upgrading to Spring Security 7.x, verify the API rather than copying code across major versions without compiling.

`AuthorizationResult.isGranted()` yields a boolean **once a result exists**. If the upstream `Mono<AuthorizationResult>` is empty, `map(AuthorizationResult::isGranted)` also produces an empty `Mono`, **not** `false`.

## 3. Write the policy expression before choosing operators

Consider the GET endpoint:

```text
/tenants/{tenantId}/documents/{documentId}
```

Policy requirements:

```text
ALLOW =
    AUTHENTICATED
    AND DOC_READ_AUTHORITY
    AND TENANT_MEMBERSHIP_VALID
    AND RESOURCE_BELONGS_TO_TENANT
    AND (OWNER_READ OR SHARED_READ)
    AND NOT_LOCKED
    AND PDP_PERMIT_VALID
```

This is an **AND across mandatory condition groups**, with a single **intentional OR** between the two ways of receiving read permission. Writing:

```java
boolean allowed = hasReadAuthority || tenantAllowed;
```

is wrong: a caller with the authority but outside the tenant could still read, or a tenant member without `DOC_READ` could read.

An expression that looks clean in Reactor can still violate the policy. Write the business truth table first:

| DOC_READ | Valid tenant | Owner | Shared | Resource unlocked | Remote permit | ALLOW |
| --- | --- | --- | --- | --- | --- | --- |
| true | true | true | false | true | true | true |
| true | true | false | true | true | true | true |
| true | false | true | true | true | true | **false** |
| false | true | true | true | true | true | **false** |
| true | true | false | false | true | true | **false** |
| true | true | true | false | false | true | **false** |
| true | true | true | false | true | false | **false** |
| true | true | true | false | true | **PDP empty/error** | **false / unavailable** |

Never use `OR` across branches that are mandatory guards. Any admin override, if permitted, must be an explicit policy-defined rule, never an `.onErrorReturn(true)` or `.switchIfEmpty(allowAll)`.

## 4. Normalize each branch: empty and error must not become true

A fail-closed helper for the example:

```java
static Mono<Boolean> denyOnMissingOrError(Mono<Boolean> check) {
    return check
            .defaultIfEmpty(false)
            .onErrorReturn(false);
}
```

Meaning:

- `true` stays true.
- `false` stays false.
- `Mono.empty()` becomes false.
- `Mono.error(...)` becomes false.

This **does not treat a PDP outage as a policy DENY**; it merely guarantees downstream never receives `true`. In production, preserve typed reason codes such as `POLICY_DENY`, `NO_DECISION`, `TIMEOUT`, and `BACKEND_ERROR`, emit metrics, and map to `Boolean` only at the enforcement boundary.

With Spring Security:

```java
Mono<AuthorizationResult> result = remoteManager
        .authorize(authentication, authorizationContext)
        .defaultIfEmpty(new AuthorizationDecision(false))
        .onErrorReturn(new AuthorizationDecision(false));
```

This is an **integration snippet**. Pass the framework-supplied `Authentication` and `AuthorizationContext`. If an error should return HTTP 503 instead of 403, use a typed exception/handler at the filter/service boundary while still preventing the protected action from running.

**Never apply an allowing fallback** such as:

```java
// WRONG: no decision or policy service error ends up granting access.
mono.defaultIfEmpty(true);
mono.onErrorReturn(true);
```

For independent guards, apply fail-closed normalization **before combining** so every branch always emits a deterministic Boolean decision.

## 5. `Mono.zip`: runs the combiner only when every source emits a value

`Mono.zip(a,b)` waits for **each `Mono` to emit a value** before emitting a tuple. If any source completes empty, the zipped result can complete empty and cancel the remaining sources; if any source errors, `zip` emits the error and cancels sibling sources accordingly.

Unsafe example:

```java
Mono<Boolean> authority = Mono.just(true);
Mono<Boolean> membership = Mono.empty();

Mono<Boolean> combined = Mono.zip(authority, membership)
        .map(pair -> pair.getT1() && pair.getT2());

// combined = Mono.empty(), does not emit false.
```

A developer might then add a dangerous line:

```java
// WRONG: permits when zip emits no value.
Mono<Boolean> allowed = combined.defaultIfEmpty(true);
```

When `membership` is `Mono.empty()`, `allowed` now emits **true**. This is an easy-to-miss "empty-to-permit" bug.

### Safe pattern

```java
Mono<Boolean> allowed = Mono.zip(
        authority.defaultIfEmpty(false),
        membership.defaultIfEmpty(false))
    .map(pair -> pair.getT1() && pair.getT2())
    .onErrorReturn(false);
```

If `authority` is `true` while `membership` is empty, `zip` still receives two Booleans (`true` and `false`) and emits `false`. If any branch errors, the pipeline never proceeds with PERMIT.

**Never zip a `Mono<Void>` as a decision source:** `Mono<Void>` completes without emitting any value, so a `zip` waiting for an item from it will never invoke the combinator.

### When multiple conditions are needed

```java
Mono<Boolean> allowed = Mono.zip(
        denyOnMissingOrError(authority),
        denyOnMissingOrError(tenant),
        denyOnMissingOrError(resource))
    .map(t -> t.getT1() && t.getT2() && t.getT3());
```

Depending on design, you may choose sequential `flatMap` so the PDP is not called if `authority`/`tenant` already denied. Never run a remote check carrying sensitive data before verifying the caller belongs to the tenant.

## 6. `flatMap`: dependent conditions should run sequentially and fail closed

Some checks depend on earlier ones. For instance, query ownership only after tenant membership is valid:

```java
Mono<Boolean> permission = authorityCheck
        .defaultIfEmpty(false)
        .flatMap(authorityOk -> {
            if (!authorityOk) {
                return Mono.just(false);
            }

            return tenantCheck
                    .defaultIfEmpty(false)
                    .flatMap(tenantOk -> {
                        if (!tenantOk) {
                            return Mono.just(false);
                        }

                        return ownerOrShareCheck
                                .defaultIfEmpty(false);
                    });
        })
        .onErrorReturn(false);
```

`flatMap` invokes its function only if upstream **emits a value**. If upstream is empty and you forget `defaultIfEmpty(false)`, the inner function **never runs**, and the result can remain empty.

Distinctions:

- `zip`: independent branches that can be subscribed concurrently (must be normalized first).
- `flatMap`: dependent steps that short-circuit on results; ideal when tenant membership must pass before querying ACLs.
- `Mono.defer`: creates the publisher at subscription time, useful for changing identity/attributes/clock/policy version; does not validate input on its own.
- `map`: transforms values synchronously; never use `map` returning `Mono<Mono<Boolean>>` thinking it flattened the publisher.

### Never call `block()` mid-reactive chain

```java
// WRONG on WebFlux event loop: can block and cause stalling.
boolean allowed = policyService.checkAccess(request).block();
```

Keep the pipeline reactive: return `Mono<AuthorizationResult>` and let the framework subscribe. If an adapter genuinely requires legacy blocking JDBC/HTTP, isolate it on a dedicated blocking scheduler and test context propagation and timeouts; prefer reactive drivers whenever feasible.

## 7. `filter` + `switchIfEmpty`: the trap that turns DENY into a fallback

`filter(predicate)` turns a `Mono.just(value)` into empty if the predicate fails. That is helpful for lookups, yet dangerous for authorization.

Counter-example:

```java
Mono<Boolean> allowed = policyDecision
        .filter(Boolean::booleanValue)
        .switchIfEmpty(Mono.just(true));
```

If `policyDecision` emits `false`, `filter` drops it. `switchIfEmpty` sees empty and emits **true**. An actual DENY was flipped into PERMIT.

Correct approach:

```java
Mono<Boolean> allowed = policyDecision
        .defaultIfEmpty(false)
        .onErrorReturn(false);
```

If using `filter` to select permitted requests in a business flow, still keep an **explicit deny** branch and never fall back to permit on empty. Never use `switchIfEmpty` as a way to "try another policy" unless a valid OR policy exists.

### When is `switchIfEmpty` valid?

In authorization APIs, a fallback can **itself be a deny decision**:

```java
Mono<AuthorizationResult> safe = policy
        .authorize(authentication, context)
        .switchIfEmpty(
                Mono.just(new AuthorizationDecision(false)));
```

Or when an **alternative** policy is explicitly designed and tested (e.g., owner OR shared), compute the outcome from both checks rather than treating missing output from check A as permission to skip it.

## 8. `Flux.all` and `Flux.any`: do not forget empty collections

For `Flux<Boolean>`:

- `all(Boolean::booleanValue)` returns `true` if **every element is true**.
- `any(Boolean::booleanValue)` returns `true` if **at least one element is true**.

On an empty flux:

```java
Flux.<Boolean>empty()
        .all(Boolean::booleanValue); // Mono.just(true)

Flux.<Boolean>empty()
        .any(Boolean::booleanValue); // Mono.just(false)
```

This is logically sound: "all elements hold" over an empty set is true (*vacuous truth*). Yet in authorization, an empty list of **missing mandatory policies** is not proof that all policies succeeded.

### Guarding when at least one check is required

```java
static Mono<Boolean> requireAll(List<Mono<Boolean>> checks) {
    if (checks.isEmpty()) {
        return Mono.just(false);
    }

    return Flux.fromIterable(checks)
            .concatMap(ReactivePolicyLab::safe)
            .all(Boolean::booleanValue);
}
```

This snippet belongs to the demo project in section 12, where `ReactivePolicyLab.safe` turns empty/error into `false`. `concatMap` preserves source order in the example; it subscribes to checks until `all` sees `false` or completes. If mandatory policies require full evaluation for auditing, design specifically for that instead of relying on an operator that short-circuits.

When **at least one permission** is required, `any` fits:

```java
Mono<Boolean> hasAny = Flux.just(
        true, false, false)
        .any(Boolean::booleanValue); // true
```

Yet never turn "at least one grant branch" into cross-tenant access. Choosing between owner and share is **one defined OR group**; tenant, authentication, and resource checks must still be ANDed outside it.

### `Flux.empty` when a service returns no permissions

An empty `Flux<Permission>` may mean "user has no permissions" or "PIP returned no data." Never call `.all(permission -> ...)` and accept `true` simply because zero permissions existed. If the business requires a non-empty permission set, check cardinality first.

## 9. `hasElement` and `hasElements` are not GRANT checks

`Mono.hasElement()` only reports whether a `Mono` emitted a value:

```java
Mono.just(false).hasElement(); // Mono.just(true)
Mono.empty().hasElement();     // Mono.just(false)
```

It does **not** report whether "decision has `isGranted=true`." Likewise, `Flux.hasElements()` only detects whether at least one item was emitted.

Counter-example:

```java
// WRONG: a DENY Mono<AuthorizationResult> also has an element.
Mono<Boolean> allowed = manager
        .authorize(authentication, context)
        .hasElement();
```

You must read `AuthorizationResult.isGranted()`:

```java
Mono<Boolean> allowed = manager
        .authorize(authentication, context)
        .map(AuthorizationResult::isGranted)
        .defaultIfEmpty(false)
        .onErrorReturn(false);
```

Never use `.count().map(count -> count > 0)` as a permission check: a DENY still counts as one emitted item.

## 10. `then`, `when`, and `Mono<Void>` can discard decisions

Operators like `then()`/`thenReturn(x)` intentionally **discard the upstream value** and care only about successful completion (or error).

Counter-example:

```java
Mono<Boolean> allowed = policyCheck
        .thenReturn(true); // WRONG: upstream false still completes normally.
```

A `Mono.just(false)` completes normally, so `thenReturn(true)` emits `true`. Similarly:

```java
Mono<Boolean> allowed = Mono.when(
        roleCheck.then(),
        tenantCheck.then())
    .thenReturn(true);
```

`Mono.when` waits for those publishers to complete, yet the Boolean results of `roleCheck`/`tenantCheck` were discarded. **Deny=`false` is not an error**, so two `false` sources still complete and the snippet above emits `true`.

Use `zip`/`flatMap` to combine actual decision values. `Mono.when` is useful for waiting on side-effecting operations to finish; it does not replace an authorization formula.

### Avoid `onErrorComplete` in policy guards

```java
// WRONG if downstream has switchIfEmpty(Mono.just(true)).
Mono<Boolean> allowed = pdpCheck
        .onErrorComplete()
        .switchIfEmpty(Mono.just(true));
```

`onErrorComplete` turns an error into empty completion; if a subsequent fallback permits, a PDP outage becomes an auth bypass. To fail closed, use `onErrorReturn(false)` or a typed failure that never leads to a grant.

## 11. Timeout, retry, and cancellation in decision chains

A PDP or ACL repository can time out. `Mono.timeout(duration)` emits a timeout error when the source fails to signal in time. Never let such an error fall into `onErrorReturn(true)` or `switchIfEmpty(permit)`.

```java
Mono<Boolean> safePdp = remotePdpCheck
        .timeout(Duration.ofMillis(300))
        .defaultIfEmpty(false)
        .onErrorResume(error -> {
            // Record appropriate metric/error code log; DO NOT log secrets.
            return Mono.just(false);
        });
```

This is an **integration snippet**, where 300 ms is illustrative; real configs need an end-to-end deadline. Import `java.time.Duration`. When the PDP is unavailable, you may return an operational 503 per contract while still preventing the protected action from running.

### Retry only when safe

Reactor's `Retry.backoff(...)` can retry transient errors. Never retry:

- A policy DENY (`false` is not an exception).
- Invalid tokens, wrong tenant/resource, or signature mismatches.
- Severe schema errors that retrying will not fix.
- Any non-idempotent mutating side effect.

Never use unbounded `retry()` for authorization checks. Bounded retries must fit inside the overall deadline. Check whether calling the PDP before verifying tenant membership leaks sensitive resource identifiers.

### Cancellation

Reactor supports cancellation; a `Mono.zip` can cancel sibling branches when one branch is empty or errors. Never rely on "every policy call definitely ran" for audit completeness. For auditing, emit a central decision event and test both emit and non-emit paths rather than using publisher subscription counts as proof of full policy evaluation.

## 12. Runnable Java 17 Maven project: Reactor decisions with fail-closed behavior

The complete example below uses **real Reactor Core** (no web server required), Spring Boot BOM for dependency version management, and JUnit 5 + `reactor-test`. Its goal is to verify operator semantics, not to mock HTTP arbitrarily.

Structure:

```text
reactive-policy-lab/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   └── ReactivePolicyLab.java
    └── test/java/demo/
        └── ReactivePolicyLabTest.java
```

### 12.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>reactive-policy-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Version `3.5.16` pins a learning project on Java 17 and matching Reactor APIs; **the Spring Boot 3.5 branch has reached end of OSS support**, so production must select a supported branch and align dependencies with its BOM. This project defines no HTTP endpoints and does not need `spring-boot-starter-security`; Spring WebFlux integration in later sections consists of **separate snippets**.

### 12.2. `ReactivePolicyLab.java`

```java
package demo;

import java.util.List;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class ReactivePolicyLab {

    private ReactivePolicyLab() {}

    // All required checks must emit a Boolean.
    // Empty/error => false. Production should retain reason codes.
    public static Mono<Boolean> safe(Mono<Boolean> check) {
        return check.defaultIfEmpty(false)
                .onErrorReturn(false);
    }

    // Role AND tenant AND (owner OR shared).
    public static Mono<Boolean> canRead(
            Mono<Boolean> authority,
            Mono<Boolean> tenant,
            Mono<Boolean> owner,
            Mono<Boolean> shared) {

        Mono<Boolean> ownerOrShare = Mono.zip(
                safe(owner), safe(shared))
                .map(pair -> pair.getT1() || pair.getT2());

        return Mono.zip(
                safe(authority),
                safe(tenant),
                ownerOrShare)
                .map(all -> all.getT1()
                        && all.getT2()
                        && all.getT3());
    }

    // An empty set of REQUIRED checks is explicitly denied.
    public static Mono<Boolean> requireAll(
            List<Mono<Boolean>> checks) {
        if (checks.isEmpty()) {
            return Mono.just(false);
        }
        return Flux.fromIterable(checks)
                .concatMap(ReactivePolicyLab::safe)
                .all(Boolean::booleanValue);
    }

    private static void scenario(String label,
                                 Mono<Boolean> authority,
                                 Mono<Boolean> tenant,
                                 Mono<Boolean> owner,
                                 Mono<Boolean> shared) {

        // block() is used only in this command-line demo program.
        boolean result = Boolean.TRUE.equals(
                canRead(authority, tenant, owner, shared).block());

        System.out.println(label + "=" + result);
    }

    public static void main(String[] args) {
        scenario("ownerAllowed",
                Mono.just(true), Mono.just(true),
                Mono.just(true), Mono.just(false));

        scenario("sharedAllowed",
                Mono.just(true), Mono.just(true),
                Mono.just(false), Mono.just(true));

        scenario("tenantDenied",
                Mono.just(true), Mono.just(false),
                Mono.just(true), Mono.just(true));

        scenario("authorityDenied",
                Mono.just(false), Mono.just(true),
                Mono.just(true), Mono.just(true));

        scenario("notOwnerAndNotShared",
                Mono.just(true), Mono.just(true),
                Mono.just(false), Mono.just(false));

        scenario("missingAuthority",
                Mono.empty(), Mono.just(true),
                Mono.just(true), Mono.just(false));

        scenario("missingOwner",
                Mono.just(true), Mono.just(true),
                Mono.empty(), Mono.just(false));

        scenario("shareError",
                Mono.just(true), Mono.just(true),
                Mono.just(false),
                Mono.error(new IllegalStateException("PIP offline")));

        System.out.println("rawAllEmpty="
                + Flux.<Boolean>empty()
                    .all(Boolean::booleanValue).block());

        System.out.println("guardedAllEmpty="
                + requireAll(List.of()).block());
    }
}
```

**Safety point:** `safe` guarantees every branch emits `true` or `false`, so `Mono.zip` never produces an unintended "empty decision." The overall condition is `authority && tenant && (owner || shared)`, not an all-OR expression. `requireAll` rejects the case where zero mandatory rules exist.

### 12.3. How to run

With JDK 17+ and Maven:

```bash
mvn -q clean test
mvn -q exec:java -Dexec.mainClass=demo.ReactivePolicyLab
```

Program stdout (excluding Maven/plugin logs):

```text
ownerAllowed=true
sharedAllowed=true
tenantDenied=false
authorityDenied=false
notOwnerAndNotShared=false
missingAuthority=false
missingOwner=false
shareError=false
rawAllEmpty=true
guardedAllEmpty=false
```

`rawAllEmpty=true` **demonstrates the `Flux.all` trap**, not an outcome to grant access with. `guardedAllEmpty=false` is the desired policy behavior when the mandatory check list is empty.

The code was checked for syntax and expected output per Reactor semantics; **no live Maven build was executed while authoring this guide**. When running in your project, if dependencies have jumped major versions, consult the Spring/Reactor migration notes.

## 13. Testing Reactor with `StepVerifier`

File `src/test/java/demo/ReactivePolicyLabTest.java`:

```java
package demo;

import java.util.List;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactivePolicyLabTest {

    @Test
    void ownerGrantNeedsAuthorityAndTenant() {
        StepVerifier.create(ReactivePolicyLab.canRead(
                    Mono.just(true), Mono.just(true),
                    Mono.just(true), Mono.just(false)))
                .expectNext(true)
                .verifyComplete();

        StepVerifier.create(ReactivePolicyLab.canRead(
                    Mono.just(true), Mono.just(false),
                    Mono.just(true), Mono.just(true)))
                .expectNext(false)
                .verifyComplete();
    }

    @Test
    void sharedGrantWorksOnlyInsideValidTenant() {
        StepVerifier.create(ReactivePolicyLab.canRead(
                    Mono.just(true), Mono.just(true),
                    Mono.just(false), Mono.just(true)))
                .expectNext(true)
                .verifyComplete();

        StepVerifier.create(ReactivePolicyLab.canRead(
                    Mono.just(false), Mono.just(true),
                    Mono.just(false), Mono.just(true)))
                .expectNext(false)
                .verifyComplete();
    }

    @Test
    void emptyDecisionNeverGrants() {
        StepVerifier.create(ReactivePolicyLab.canRead(
                    Mono.<Boolean>empty(), Mono.just(true),
                    Mono.just(true), Mono.just(false)))
                .expectNext(false)
                .verifyComplete();

        StepVerifier.create(ReactivePolicyLab.canRead(
                    Mono.just(true), Mono.<Boolean>empty(),
                    Mono.just(true), Mono.just(true)))
                .expectNext(false)
                .verifyComplete();
    }

    @Test
    void errorDecisionNeverGrants() {
        StepVerifier.create(ReactivePolicyLab.canRead(
                    Mono.just(true), Mono.just(true),
                    Mono.just(false),
                    Mono.error(new IllegalStateException("PIP failed"))))
                .expectNext(false)
                .verifyComplete();
    }

    @Test
    void ownerAndShareBothMissingDoNotGrant() {
        StepVerifier.create(ReactivePolicyLab.canRead(
                    Mono.just(true), Mono.just(true),
                    Mono.<Boolean>empty(), Mono.<Boolean>empty()))
                .expectNext(false)
                .verifyComplete();
    }

    @Test
    void emptyAllMustBeRejectedByContract() {
        StepVerifier.create(
                    Flux.<Boolean>empty().all(Boolean::booleanValue))
                .expectNext(true)   // Reactor semantics, NOT policy.
                .verifyComplete();

        StepVerifier.create(ReactivePolicyLab.requireAll(List.of()))
                .expectNext(false)
                .verifyComplete();
    }

    @Test
    void requiredChecksAreConjoined() {
        StepVerifier.create(ReactivePolicyLab.requireAll(
                    List.of(Mono.just(true),
                            Mono.just(true),
                            Mono.just(false))))
                .expectNext(false)
                .verifyComplete();

        StepVerifier.create(ReactivePolicyLab.requireAll(
                    List.of(Mono.just(true), Mono.just(true))))
                .expectNext(true)
                .verifyComplete();
    }

    @Test
    void hasElementIsNotSameAsGranted() {
        StepVerifier.create(Mono.just(false).hasElement())
                .expectNext(true)
                .verifyComplete();
    }
}
```

The test suite contains **8 JUnit 5 methods** (some with multiple assertions). It verifies:

- An owner/share grant cannot bypass mandatory tenant or authority checks.
- Empty/error in any policy branch never becomes PERMIT.
- `Flux.all` on an empty set evaluates to `true` and an explicit guard prevents it.
- `hasElement` on a DENY=`false` is still `true`; it must never serve as an authorization result.

After running `mvn test`, inspect Surefire reports in `target/surefire-reports`. Never flip an expected `false` to `true` just to make a test green when a regression appears; that would hide a security flaw.

### Testing harder cases

Add tests using `StepVerifier.withVirtualTime` to verify `Mono.timeout`/retries without real waiting. Add `PublisherProbe` when you must confirm a policy branch was not subscribed to after tenant/authority already denied. For delayed or side-effecting sources, verify cancellation and total remote PDP call counts.

`StepVerifier` is for Reactor unit tests; it does not replace `WebTestClient` verifying real HTTP filter chains and resource security.

## 14. Integrating Spring Security `ReactiveAuthorizationManager`

In WebFlux, `ServerHttpSecurity.authorizeExchange(...)` accepts `.access(ReactiveAuthorizationManager<AuthorizationContext>)`. The interface receives `Mono<Authentication>` and the exchange's authorization context.

The snippet below is **integration code for Spring Security 6.5**, not part of the `reactive-policy-lab` project (which depends only on Reactor/JUnit). It shows a manager blocking all non-PERMIT outcomes. Because the 6.5 interface still has an abstract/deprecated `check`, the class implements both `check` and `authorize`; when upgrading to 7.x, verify the new interface signature and remove overrides that no longer exist.

```java
import reactor.core.publisher.Mono;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.server.authorization.AuthorizationContext;

final class DocumentReactiveGate
        implements ReactiveAuthorizationManager<AuthorizationContext> {

    private final DocumentReactivePolicy policy;

    DocumentReactiveGate(DocumentReactivePolicy policy) {
        this.policy = policy;
    }

    // Spring Security 6.5 compatible.
    @Override
    public Mono<AuthorizationDecision> check(
            Mono<Authentication> authentication,
            AuthorizationContext context) {
        return decide(authentication, context)
                .map(AuthorizationDecision::new);
    }

    @Override
    public Mono<AuthorizationResult> authorize(
            Mono<Authentication> authentication,
            AuthorizationContext context) {
        return decide(authentication, context)
                .map(allowed ->
                        (AuthorizationResult) new AuthorizationDecision(allowed));
    }

    private Mono<Boolean> decide(
            Mono<Authentication> authentication,
            AuthorizationContext context) {

        return authentication
                .filter(auth -> auth.isAuthenticated()
                        && !(auth instanceof AnonymousAuthenticationToken))
                .flatMap(auth -> policy.canRead(
                        auth, context.getExchange()))
                .defaultIfEmpty(false)
                .onErrorReturn(false);
    }
}
```

`DocumentReactivePolicy` is a **business service** you must implement; Spring does not automatically know your project's memberships, owners/shares, or PDP. `canRead(Authentication, ServerWebExchange)` returns `Mono<Boolean>` and is **true only after all mandatory guards pass**. If 503 is needed on PDP outages, use dedicated typed failure mapping at the filter/service boundary without turning errors into `true`.

### Why use the framework-supplied `Mono<Authentication>`?

- Never extract usernames or roles from client-supplied headers.
- Spring Security Reactive propagates context per subscriber, without relying on `ThreadLocal` keeping the right identity across thread hops.
- `authentication` may be empty if unauthenticated; `defaultIfEmpty(false)` ensures non-permit.
- If guest endpoints need access, configure explicit `permitAll`; protected endpoints must never let guests through on empty authentication.

Never globally cache `Mono<Authentication>` or `policy.canRead(...)` results across requests. A shared cached publisher can replay another caller's decision if scoped wrongly.

## 15. `SecurityWebFilterChain` and matcher ordering

Reactive HTTP configuration example:

```java
@Bean
SecurityWebFilterChain apiSecurity(
        ServerHttpSecurity http,
        DocumentReactiveGate documentGate) {

    return http
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/public/**").permitAll()
                    .pathMatchers(
                        HttpMethod.GET,
                        "/tenants/*/documents/*")
                    .access(documentGate)
                    .anyExchange().denyAll())
            .oauth2ResourceServer(resource ->
                    resource.jwt(Customizer.withDefaults()))
            .build();
}
```

Requires imports for `@Bean`, `HttpMethod`, `ServerHttpSecurity`, `SecurityWebFilterChain`, and `Customizer`. The application needs `spring-boot-starter-webflux`, `spring-boot-starter-security`, and JWT Resource Server dependencies/configuration with valid issuer/audience; this is an integration snippet only.

Inside `authorizeExchange`, **matcher order matters**. Writing:

```java
.anyExchange().permitAll()
.pathMatchers("/tenants/**").access(documentGate)
```

is broken: a broad rule upfront prevents later guarding rules from ever being evaluated or fails configuration validation depending on DSL/version. Place specific rules first and `anyExchange().denyAll()` last. WebFlux typically binds `pathMatchers(...).access(manager)` per route family; rules listed for different exchanges are not automatically ANDed together.

**Servlet vs reactive distinction:**

| Servlet MVC | Reactive WebFlux |
| --- | --- |
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `authorizeHttpRequests` | `authorizeExchange` |
| `AuthorizationManager<RequestAuthorizationContext>` | `ReactiveAuthorizationManager<AuthorizationContext>` |
| `SecurityContextHolder` typically per thread | `ReactiveSecurityContextHolder` via Reactor Context |
| Blocking servlet repositories are generally expected by config | Avoid blocking on the event loop; use reactive repositories/adapters |

Never take a servlet sample and merely rename `HttpSecurity` to `ServerHttpSecurity`; manager signatures and authentication flows differ.

## 16. Tenant and resource permissions must be computed from verified data

A policy can be written as:

```text
authenticated
AND hasAuthority("DOC_READ")
AND requestTenant ∈ activeMemberships(subject)
AND resource.tenantId == authorizedTenant
AND (owner == subject OR validShare(subject, resource))
AND resource.status != LOCKED
```

**Tenant checks must run before owner/share checks.** A record with the same local document ID in another tenant must never be granted.

Java reactive policy pseudocode pattern:

```java
Mono<Boolean> canRead(Authentication auth, ServerWebExchange exchange) {
    return tenantResolver.resolveVerified(auth, exchange)
            .flatMap(scope ->
                documentRepository.findByIdAndTenant(
                        documentIdFromRoute(exchange),
                        scope.tenantId())
                    .flatMap(doc ->
                        Mono.zip(
                            authorityCheck(auth, "DOC_READ"),
                            ownerOrShareCheck(auth, scope, doc),
                            unlockedCheck(doc))
                        .map(t -> t.getT1() && t.getT2() && t.getT3())
                    )
            )
            .defaultIfEmpty(false)
            .onErrorReturn(false);
}
```

This is **integration pseudocode**: `tenantResolver` must verify membership server-side, `documentIdFromRoute` must validate input, `documentRepository` must scope queries by tenant, and each check must be defined concretely. In real code, normalize **each individual branch** before `zip`, not just the outer `defaultIfEmpty(false)`, so non-decisions and errors are never handled unexpectedly. For remote PDP errors, typed outcomes distinguish outages from policy DENY.

### Query-time enforcement is still necessary

Even when the HTTP manager allows a request, repositories must never call `findById(id)` relying solely on the earlier policy check if the resource could change tenant or owner between check and read. Use tenant-scoped queries, transaction/version predicates, and least privilege; apply the same row-level scoping to search, count, and stats queries. HTTP authorization does not automatically append `WHERE tenant_id = ...`.

## 17. Do not let scheduler switches drop identity or tenant scope

In WebFlux, execution can jump between the event loop, `Schedulers.parallel()`, and `Schedulers.boundedElastic()`. `ThreadLocal` typically does not reflect the subscriber's identity. Use `ReactiveSecurityContextHolder` for the reactive `SecurityContext`, and Reactor `Context` to carry a **resolved authorized tenant scope** if needed by downstream services.

```java
static final String SCOPE_KEY = "authorizedTenantScope";

Mono<Document> read(AuthorizedTenantScope scope) {
    return Mono.deferContextual(context -> {
        AuthorizedTenantScope actual = context.get(SCOPE_KEY);
        return repository.findByIdAndTenant(
                scope.documentId(), actual.tenantId());
    }).contextWrite(ctx -> ctx.put(SCOPE_KEY, scope));
}
```

This is a **conceptual snippet**, needing definitions for `AuthorizedTenantScope` (including resource ID if used as above), `Document`, and the repository—not a standalone program. Reactor Context stores per-subscription state and **does not authenticate tenants by itself**. Put only membership/policy-verified data into it; never write a raw `X-Tenant-Id` into `contextWrite` and treat it as authorized.

### Prefer passing scope via explicit parameters whenever possible

`repository.findByIdAndTenant(id, authorizedTenantId)` is easier to audit than reading from an implicit context. Reactor Context is helpful for tracing and security context, yet should not hide whether permissions were actually verified.

### Never place `block()` inside the pipeline

Calling `block()` inside WebFlux can stall the event loop, exhaust threads, and break context propagation. When integrating legacy blocking libraries, wrap them in `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` while preserving tenant policies, deadlines, and cancellation per design; never treat `boundedElastic` as an excuse to skip authorization.

## 18. Subscription, `defer`, and `Mono.cache`: which request owns the decision?

Reactor publishers are usually **cold**: they execute no logic until subscribed. Yet you can accidentally capture a value too early or cache a decision too broadly.

Counter-example:

```java
// WRONG: the decision could be reused across multiple calls/users
// if the shared Mono is cached and reused globally.
Mono<Boolean> sharedCachedPermission =
        policyService.canRead(currentUser, document)
                .cache();
```

`Mono.cache()` caches the result/error/completion across subscribers of the **same instance**. If that instance lives in a singleton and is not keyed by subject+tenant+resource+action+version, Alice's decision can be replayed to Bob.

Correct pattern:

```java
Mono<Boolean> authorizationForThisRequest =
        Mono.defer(() -> policyService.canRead(
                verifiedPrincipal, resource, action));
```

`Mono.defer` constructs a fresh publisher per subscription; it **does not replace principal/resource verification**. If business caching is used, keys must include tenant, subject/authority, resource ID, and version/expiry; permission revocation requires invalidation or a TTL matching your SLA.

### Cancellation and "called the PDP" do not equal "permitted"

`zip`/`flatMap` can cancel upstream; audit logs must record the **final enforcement outcome**, not merely count "PDP was subscribed." If a request cancels after the policy check, do not let a background mutation continue without its required guards and transactions.

## 19. Test matrix before deploying real endpoints

| Case | Authority | Tenant | Owner | Shared | PDP / data | Expected |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | true | true | true | false | PERMIT | ALLOW |
| 2 | true | true | false | true | PERMIT | ALLOW |
| 3 | false | true | true | true | PERMIT | DENY |
| 4 | true | false | true | true | PERMIT | DENY |
| 5 | true | true | false | false | PERMIT | DENY |
| 6 | true | true | true | false | DENY | DENY |
| 7 | true | true | true | false | PDP `Mono.empty()` | DENY |
| 8 | true | true | true | false | PDP `Mono.error()` | DENY/unavailable |
| 9 | true | `Mono.empty()` | true | false | PERMIT | DENY |
| 10 | `Mono.empty()` | true | true | false | PERMIT | DENY |
| 11 | true | true | false | `Mono.error()` | PERMIT | DENY/unavailable |
| 12 | true | true | true | false | Resource not found | DENY/404 per contract |
| 13 | true | true | true | false | Wrong tenant resource | DENY |
| 14 | true | true | true | false | Locked | DENY |
| 15 | true | true | true | false | Wrong PDP action/resource | DENY/invalid |
| 16 | true | true | true | false | PDP timeout | DENY/unavailable |
| 17 | true | true | true | false | PDP response expired | DENY/invalid |
| 18 | true | true | true | false | Empty required check list | DENY |
| 19 | true | true | true | false | `Flux.all` empty source | Test catches `true` while policy guard denies |
| 20 | true | true | true | false | Reused cached permission from another user | DENY; test cache isolation |

These cases require combining **both local and remote PDP** tests in production; the Maven project in section 12 tests only authority, tenant, owner/shared, and operator traps. Do not claim it tested an HTTP filter chain or remote PDP.

### `WebTestClient`

In WebFlux, use `WebTestClient` to verify:

- `GET /public/info` is permitted per public policy.
- `GET /tenants/alpha/documents/42` without auth → 401.
- Authenticated Alice with `DOC_READ`, valid tenant, owner/shared → succeeds.
- Alice in `alpha` requesting path tenant `beta` → 403/404 per contract.
- Policy service `Mono.empty`/error/timeout → never returns protected content and never invokes handler service.
- Wrong resource ID, resource tenant mismatch, or locked document → leaks no data.
- HTTP status mapping when the PDP is unavailable if the app chooses 503.

`WebTestClient` and `@WithMockUser` verify Spring Security integration, yet mock auth **does not verify real JWT signatures**. For resource servers, add decoder/security filter tests using signed test-key JWTs and verifying issuer/audience.

### `StepVerifier` must test empty/error, not only true/false

A test suite using only `Mono.just(true)` and `Mono.just(false)` is insufficient: bugs hide in `Mono.empty()`, `Mono.never()`, `Mono.error()`, cancellation, and timeouts. For `Mono.never()`, use virtual time or explicit timeout assertions so the test suite cannot hang.

## 20. Common mistakes when combining Reactor operators

**1. `zip` with one empty branch and an outer `defaultIfEmpty(true)`.** Missing decision becomes PERMIT.

**2. `filter(isGranted).switchIfEmpty(Mono.just(PERMIT))`.** A real DENY becomes empty, and the fallback grants access.

**3. `Flux.all(...)` on an empty set.** Returns `true` by vacuous truth; require non-empty mandatory rule lists.

**4. `hasElement()/hasElements()` instead of `isGranted()`.** A DENY is still an emitted element.

**5. `thenReturn(true)` after `Mono.just(false)`.** Discards the boolean DENY and emits PERMIT.

**6. `Mono.when(...)` to combine Boolean conditions.** Waits only for completion without ANDing decisions.

**7. `onErrorReturn(true)` or `onErrorComplete().switchIfEmpty(permit)`.** A PDP outage becomes an auth bypass.

**8. Using OR for two mandatory guards.** `role || tenant` lets callers lacking tenant membership or lacking the role through.

**9. Using `Flux.any(...)` across all mandatory checks.** One passing check grants access even when other checks deny.

**10. Treating `Mono.empty()` in `ReactiveAuthorizationManager` as a "guaranteed DENY."** It means no decision was produced; compositions may interpret it differently.

**11. Calling a remote PDP before checking tenant membership.** Can send unverified resource/tenant attributes to the PDP and waste resources.

**12. Calling `block()` on the WebFlux event loop.** Stalls requests and destroys non-blocking benefits.

**13. Using Servlet thread-local `SecurityContextHolder` in a reactive chain.** Identity breaks across thread hops; use reactive security context.

**14. Using `Mono.cache()` for a shared authorization result across users.** One caller's decision gets replayed to another caller.

**15. Testing only the happy path.** Misses empty, error, timeout, no-decision, and cancellation bugs.

**16. Omitting a trailing `anyExchange().denyAll()`.** Newly added endpoints may lack expected protection.

**17. Thinking two consecutive `pathMatchers` act like AND.** HTTP rule matching follows precedence; to AND policies, build a proper composite manager/policy.

**18. Endpoint permissions without tenant-scoped data queries.** Out-of-scope reads/counts/stats can occur right after HTTP policy permits.

**19. Ignoring obligations/attributes when the PDP returns PERMIT.** Authorization succeeds only when the full policy contract is satisfied.

**20. Failing to distinguish policy DENY from infrastructure errors.** Both block business execution, yet logging, monitoring, and status mapping should differ.

## 21. Production checklist

- [ ] Write the business Boolean formula, clearly distinguishing AND groups from OR groups.
- [ ] Every mandatory guard yields an explicit decision; empty/error never becomes allow.
- [ ] Normalize `Mono.empty()` to deny before `zip` where appropriate.
- [ ] Never use `defaultIfEmpty(true)`/`onErrorReturn(true)` in authorization.
- [ ] Never use `filter(...).switchIfEmpty(permit)` on a decision.
- [ ] Never use `thenReturn(true)`/`hasElement()` to evaluate access.
- [ ] For `Flux.all`, handle empty check lists per policy rather than relying on vacuous truth.
- [ ] Apply `Flux.any` only to approved alternative grant groups.
- [ ] Dependent chains use `flatMap` to verify tenant/role before calling resource/PDP lookups.
- [ ] Handle timeouts, cancellations, and bounded retries without ever opening access.
- [ ] `ReactiveAuthorizationManager` returns explicit decisions for protected endpoints.
- [ ] `ServerHttpSecurity.authorizeExchange` matches routes accurately and ends with `denyAll`.
- [ ] Never mix Servlet `AuthorizationManager` with reactive managers.
- [ ] Obtain `Authentication` from Spring Security reactive sources, never raw requests/headers.
- [ ] Resolve tenants via server-side membership and query resources with tenant predicates.
- [ ] Never block the event loop; use reactive drivers or properly isolated blocking adapters.
- [ ] Never cache decisions across caller/tenant/resource/action; set appropriate TTLs/versions.
- [ ] Write `StepVerifier` tests for true, false, empty, error, timeout, and empty lists.
- [ ] Write `WebTestClient` tests for HTTP 401/403/503 and verify zero side effects.
- [ ] Run regression tests after Spring Security/Reactor upgrades, especially `check` → `authorize`.

**Conclusion:** Reactor handles **values, empty completions, errors, and cancellations**, not just true/false. To combine decisions safely in WebFlux HTTP, normalize every mandatory branch into an **explicit decision**, apply **policy-accurate AND/OR logic**, block empty/error/timeout fallbacks, and grant access only when **all mandatory guards** truly succeed. An operator with completely valid Reactor semantics can still create an **authorization vulnerability** if used as a grant check contrary to its actual behavior.

## Official documentation

- [Spring Security — Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — ReactiveAuthorizationManager JavaDoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Project Reactor — Reactor Core Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [Project Reactor — FAQ: Mono zipWith/zipWhen never called](https://projectreactor.io/docs/core/release/reference/faq.html)
- [Project Reactor — Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Project Reactor — Mono JavaDoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
