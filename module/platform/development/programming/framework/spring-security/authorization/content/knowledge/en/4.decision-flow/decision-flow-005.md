# AuthorizationDecision, AuthorizationResult, and Version-Appropriate APIs in Spring Security

## 1. Objective: understand the authorization result before choosing an API

When a request passes through Spring Security, the system must answer: **is the current principal allowed to perform the action on the resource under consideration?** That result is neither an `Authentication` object nor an HTTP `403` status code. In the modern authorization mechanism, `AuthorizationManager` evaluates the request and returns an **authorization result**. The enforcement layer (HTTP filter, method interceptor, message security, etc.) then uses that result to allow continuation or deny access.

This lesson focuses on three concepts:

- `AuthorizationDecision` — the **concrete result class** representing allow/deny.
- `AuthorizationResult` — the **result interface** featuring `isGranted()`, preventing APIs from being locked to a single class.
- `AuthorizationManager<T>` — the **evaluator** receiving `Supplier<Authentication>` and a context object of type `T`; method signatures change across Spring Security versions.

After this lesson, you will be able to:

1. Distinguish an authorization result from the evaluator, exceptions, and HTTP status codes.
2. Read and write `check(...)`/`authorize(...)`/`verify(...)` correctly for your library version.
3. Understand why `AuthorizationResult` exists even though legacy code still returns `AuthorizationDecision`.
4. Implement a custom HTTP `AuthorizationManager` using the APIs of Spring Security 6.3, 6.4–6.5, and 7.x without mixing signatures.
5. Choose an appropriate integration among `authorizeHttpRequests`, `@PreAuthorize`, and custom policies.
6. Write tests for `ALLOW`, `DENY`, and `null`/abstain risks, rather than testing status codes alone.

**Core note:** class names and APIs change across versions. Do not copy snippets verbatim from the "current" documentation branch into a project running Spring Security 6.3 or 6.5 without checking your actual dependencies.

## 2. Spring Security's decision model

```text
HTTP request / method invocation / message
                  │
                  ▼
        Current Authentication
    (identity + GrantedAuthority)
                  │
                  ▼
           AuthorizationManager<T>
        ┌─────────────────────────┐
        │ Supplier<Authentication>│
        │ secure object/context T │
        │ business policy         │
        └────────────┬────────────┘
                     │
             AuthorizationResult
               /           \
          granted=true   granted=false
               │             │
               ▼             ▼
      continue processing  deny access
                         (exception/filter)
```

**Four parts to keep separate:**

| Component | Responsibility | Example |
| --- | --- | --- |
| `Authentication` | Logged-in principal or active authentication mechanism, with authorities | `ROLE_EDITOR`, `document:read` |
| `T` in `AuthorizationManager<T>` | Object/metadata requiring permission check | `RequestAuthorizationContext`, `MethodInvocation` |
| `AuthorizationManager<T>` | Executes the authorization policy | Checks permissions, tenant, resource state |
| `AuthorizationResult` / `AuthorizationDecision` | Indicates **whether permission is granted or not** | `new AuthorizationDecision(true)` |

`AuthorizationResult` does not load users or decode JWTs. `AuthorizationDecision` does not block requests by itself. Actual denial happens where the authorization result is **consumed**.

Functional decisions and object-level decisions can be combined: having `document:edit` is a necessary condition; when editing `document d7`, the service must still check owner, tenant, and document state. A custom manager can use that additional data, but the framework **does not automatically know** domain rules unless the application implements them.

## 3. Distinguishing AuthorizationDecision and AuthorizationResult

### 3.1. AuthorizationDecision — an instantiable class

`AuthorizationDecision` resides in package:

```text
org.springframework.security.authorization.AuthorizationDecision
```

A typical allow/deny decision:

```java
AuthorizationDecision allow = new AuthorizationDecision(true);
AuthorizationDecision deny  = new AuthorizationDecision(false);

boolean a = allow.isGranted();  // true
boolean d = deny.isGranted();   // false
```

The class provides the `AuthorizationDecision(boolean granted)` constructor and `isGranted()`. When policy code only needs to return true/false, this is a simple, explicit representation.

### 3.2. AuthorizationResult — the contract interface

`AuthorizationResult` is in the same package, provides `isGranted()`, and extends `Serializable`. It was introduced in the **Spring Security 6.3** line. `AuthorizationDecision` **implements `AuthorizationResult`**.

```java
AuthorizationResult result = new AuthorizationDecision(true);
System.out.println(result.isGranted()); // true
```

The snippet above only applies when the project includes `AuthorizationResult` (6.3 or later). Returning an interface type lets the framework and applications use different result types instead of forcing every result to be `AuthorizationDecision`.

**Avoid misunderstandings:**

- `AuthorizationResult` is an **interface**; never write `new AuthorizationResult(...)`.
- `AuthorizationDecision` is a **class**; it can be created with `new AuthorizationDecision(boolean)`.
- `AuthorizationResult` is not a new type that "completely replaces" `AuthorizationDecision`; the concrete class remains a valid way to create results in modern versions.
- Even as many APIs return `AuthorizationResult`, you can still return `new AuthorizationDecision(allowed)` because it implements that interface.

### 3.3. Reading results without casting

**Recommended** when an API returns `AuthorizationResult`:

```java
AuthorizationResult result = manager.authorize(authenticationSupplier, context);
boolean allowed = result != null && result.isGranted();
```

The check above **deliberately fails closed in custom application code**: `null` is not treated as allow. It is an illustrative pattern for your application to make a definite decision, not a claim that every framework interceptor always interprets `null` as deny.

**Avoid**:

```java
AuthorizationDecision decision =
        (AuthorizationDecision) manager.authorize(authenticationSupplier, context);
```

Reason: the API publishes `AuthorizationResult` and does not promise every implementation returns `AuthorizationDecision` specifically. Casting can throw `ClassCastException` when another subclass/result type is used. Prefer calling `isGranted()` on the interface, or accessing extra data per the concrete implementation's contract if needed.

### 3.4. A DENY result does not immediately equal an exception

`new AuthorizationDecision(false)` is only **denial decision data**. Depending on where it is used, the enforcement component may throw `AccessDeniedException`, halt the method, handle an event, or turn it into HTTP `403`. A manager returning false **does not send an HTTP response by itself**.

Conversely, `verify(...)` is a convenience API on `AuthorizationManager`: it evaluates the policy and can **throw `AccessDeniedException` when denied**. When you only need the result for logging, testing, or policy composition, use the version-appropriate `authorize(...)`; when the goal is to enforce permission or fail with an exception, consider `verify(...)`.

## 4. Version matrix: 6.3, 6.4–6.5, and 7.x

This is the most important part of the lesson:

| Spring Security line | Primary method on `AuthorizationManager<T>` | Return type | Notes |
| --- | --- | --- | --- |
| **6.3.x** | `check(Supplier<Authentication>, T)` | `AuthorizationDecision` (nullable) | `check` is the abstract method; **`authorize` does not exist on this interface yet** |
| **6.4.x** | `authorize(Supplier<Authentication>, T)` | `AuthorizationResult` (nullable) | `authorize` was **added as a default method**; `check` remains but is **deprecated** |
| **6.5.x** | `authorize(Supplier<Authentication>, T)` | `AuthorizationResult` (nullable) | `check` still exists/deprecated; to implement the interface, `check` remains the abstract method in 6.5 Javadocs |
| **7.0+** | `authorize(Supplier<? extends Authentication>, T)` (nullability annotations may appear in Javadoc) | `AuthorizationResult` (nullable) | `authorize` is the **abstract method**; `check` **has been removed from the interface** |

**Distinguish two milestones:**

- Spring Security **6.3**: has the `AuthorizationResult` type, but `AuthorizationManager` still uses `check(...)`.
- Spring Security **6.4**: added `AuthorizationManager.authorize(...)` and deprecated `check(...)` so the API returns the `AuthorizationResult` interface.
- Spring Security **7.x**: removed `check(...)` from the interface, using `authorize(...)` as the implementation point.

Do not confuse when **the interface was introduced** with when **the `AuthorizationManager` signature changed**. In an older project, code using `check` may still be right for that version; in a new project, do not use old `check` examples as the default template.

### 4.1. Same names, different roles: check, authorize, verify

```text
6.3:
  AuthorizationDecision check(Supplier<Authentication>, T)
  default void verify(Supplier<Authentication>, T)

6.4 / 6.5:
  @Deprecated AuthorizationDecision check(Supplier<Authentication>, T)
  default AuthorizationResult authorize(Supplier<Authentication>, T)
  default void verify(Supplier<Authentication>, T)

7.x:
  AuthorizationResult authorize(Supplier<? extends Authentication>, T)
  default void verify(Supplier<? extends Authentication>, T)
  [check() is no longer an interface member]
```

The signatures above show the general form, omitting annotations for readability. When copying code, verify against the **Javadoc matching the version managed by your BOM/parent POM**. Spring Boot in particular manages the Spring Security version; do not infer it from your Java version or from an internet snippet.

### 4.2. Implications when writing a custom manager

In **6.3** and **6.4–6.5**, writing:

```java
@Override
public AuthorizationDecision check(
        Supplier<Authentication> authentication, T context) {
    return new AuthorizationDecision(true);
}
```

satisfies the interface's abstract method in those lines. In 6.4–6.5, code calling `authorize(...)` can use the default implementation inherited from the interface, depending on the manager. **Do not change it to only override `authorize` and delete `check` in 6.5** if that interface still requires `check`; the project may fail to compile because the class does not implement the abstract method.

In **7.x**, the interface requires implementing `authorize(...)`:

```java
@Override
public AuthorizationResult authorize(
        Supplier<? extends Authentication> authentication, T context) {
    return new AuthorizationDecision(true);
}
```

The illustration uses generic type `T`; real implementations must specify `T` on the class, such as `RequestAuthorizationContext`. When upgrading from 6.5 to 7, update the implemented method and check the build; an `@Override` on `check` will fail because the method is no longer on the interface.

### 4.3. Why can't you paste one implementation for all versions?

There are differences in **abstract/default methods** and **generic signatures**. Code that "looks identical" can:

- Compile on 6.5 because it implements `check`, yet fail to implement the mandatory `authorize` on 7.
- Call `authorize` in a 6.3 module, causing a **cannot find symbol** error.
- Override 6.5's `authorize(Supplier<Authentication>, ...)` in a 7.x class that has a different wildcard signature, causing **name clash**/**does not override** errors depending on the code.
- Be tested against one version only and then applied across a repository where services use different BOMs.

**Reliable approach:** each module selects the exact API for its resolved dependency; upgrade step by step with compilation + integration tests. For public libraries supporting multiple lines, consider version-specific adapters/modules instead of arbitrary casting or reflection.

## 5. `null`, abstain, and the fail-closed principle

The Javadoc allows a `null` return when a manager **makes no decision** (abstain). This is **not** strictly equivalent to `new AuthorizationDecision(false)`:

| Result | Meaning at the policy layer | Safe interpretation in custom app code |
| --- | --- | --- |
| `new AuthorizationDecision(true)` | Positive grant decision | ALLOW, if other mandatory conditions pass |
| `new AuthorizationDecision(false)` | Negative deny decision | DENY |
| `null` | No decision / abstain | Never treat as allow; requires explicit combination rules |

In some interceptors or combinators, abstain can behave differently from a negative decision. Documentation for `AuthorizationManager.verify` describes throwing an exception on a **negative** decision, so do not assume `null` is always blocked identically to false everywhere.

For policies protecting sensitive data, **return an explicit result** and configure a deny fallback:

```java
boolean allowed = actor != null
        && actorHasPermission(actor, "document:read")
        && sameTenant(actor, document)
        && canReadObject(actor, document);
return new AuthorizationDecision(allowed);
```

This is a **pseudocode method body**; `actorHasPermission`, `sameTenant`, and `canReadObject` are defined by the application. If the actor/resource is missing or the repository errors, never return allow by default. Depending on business rules, infrastructure errors may be distinguished from access denied, but permission must never be granted accidentally.

### 5.1. Never force "null = DENY" and assume the framework does the same

In application code that invokes a manager directly, you can choose:

```java
AuthorizationResult result = manager.authorize(authSupplier, resource);
boolean explicitlyGranted = result != null && result.isGranted();
```

This is an **application-defined fail-closed policy**, not a description of implicit behavior across the entire framework. When writing a custom `AuthorizationManager`, it is best to avoid `null` unless intentionally designing an abstain mechanism with clear combination/terminal rules.

### 5.2. Never rely solely on HTTP status codes

- `401 Unauthorized` typically reflects being unauthenticated on an API requiring authentication.
- `403 Forbidden` typically reflects an authenticated caller lacking permission.
- `404 Not Found` is sometimes intentionally used by products to avoid disclosing a resource's existence.

Exact codes depend on `AuthenticationEntryPoint`, `AccessDeniedHandler`, CSRF, and the API contract. **`AuthorizationDecision`/`AuthorizationResult` types are not HTTP codes**, so policy unit tests and HTTP integration tests should be kept distinct.

## 6. Code examples for Spring Security 6.3 through 6.5

### 6.1. Custom HTTP AuthorizationManager in 6.3, 6.4, and 6.5

Example protecting report reading based on the `report:read` authority. This is **integration code inside a Spring Security Servlet project** with all dependencies present, not runnable with plain `javac`.

Create a class in your application package:

```java
import java.util.function.Supplier;

import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

public final class ReportReadAuthorizationManager
        implements AuthorizationManager<RequestAuthorizationContext> {

    @Override
    public AuthorizationDecision check(
            Supplier<Authentication> authentication,
            RequestAuthorizationContext context) {

        // get() may return null or throw an exception if there is no Authentication.
        Authentication current;
        try {
            current = authentication.get();
        } catch (AuthenticationCredentialsNotFoundException ex) {
            return new AuthorizationDecision(false);
        }

        boolean allowed = current != null
                && current.getAuthorities().stream().anyMatch(authority ->
                        "report:read".equals(authority.getAuthority()));

        return new AuthorizationDecision(allowed);
    }
}
```

Here `AuthenticationCredentialsNotFoundException` is caught illustratively to **fail closed**; a real application should decide whether to let `AuthenticationException` propagate to the entry point mechanism. Never catch general `Exception` and return allow. Token/session validation and authority mapping must occur before the custom manager evaluates. Without `report:read`, the result is `false`.

**Version level:**

- This `check` matches the abstract signature in **6.3**.
- In **6.4–6.5**, `check` still compiles but produces a `@Deprecated` warning; the interface provides default `authorize(...)` for callers.
- This snippet is **not a verbatim implementation for 7.x**.

**Migration management option for 6.4–6.5:** you can keep overriding `check` while new callers use `authorize` (default). If complex code needs complete control over the result, check the Javadoc/behavior of the specific manager; do not assume every subclass is invoked through the exact same path.

### 6.2. HTTP configuration using the manager

In a `@Configuration` class, create/inject the `ReportReadAuthorizationManager` bean and use it:

```java
@Bean
SecurityFilterChain filterChain(
        HttpSecurity http,
        ReportReadAuthorizationManager reportReadManager) throws Exception {

    return http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/reports/*")
                .access(reportReadManager)
            .anyRequest().denyAll()
    ).build();
}
```

This is a **Spring Security Servlet fragment**, requiring imports for `@Bean`, `SecurityFilterChain`, `HttpSecurity`, `HttpMethod`, and the registered manager bean/component. The check principle is authorization via `AuthorizationManager<RequestAuthorizationContext>` for a specific route, without writing HTTP responses inside the manager.

If no specialized policy is needed, the shorter built-in form is:

```java
.requestMatchers(HttpMethod.GET, "/api/reports/*")
    .hasAuthority("report:read")
```

Do not write a custom manager merely to replace `hasAuthority` when no extra policy is needed. The custom example is used here to clearly observe return types and integration.

## 7. Code example for Spring Security 7.x

In Spring Security **7.x**, `AuthorizationManager.check(...)` is no longer an interface member. Implementations must override `authorize(...)` and can return `AuthorizationResult`. The following is a **replacement class** for the 6.x class—do not place both classes with the same name in the same package simultaneously:

```java
import java.util.function.Supplier;

import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

public final class ReportReadAuthorizationManager
        implements AuthorizationManager<RequestAuthorizationContext> {

    @Override
    public AuthorizationResult authorize(
            Supplier<? extends Authentication> authentication,
            RequestAuthorizationContext context) {

        Authentication current;
        try {
            current = authentication.get();
        } catch (AuthenticationCredentialsNotFoundException ex) {
            return new AuthorizationDecision(false);
        }

        boolean allowed = current != null
                && current.getAuthorities().stream().anyMatch(authority ->
                        "report:read".equals(authority.getAuthority()));

        return new AuthorizationDecision(allowed);
    }
}
```

`AuthorizationResult` is the interface, while `new AuthorizationDecision(allowed)` is a valid implementation. `authorize(...)` in the 7.x snippet is the required method to implement; `check(...)` is no longer a method to override.

The same `SecurityFilterChain` fragment from section 6.2 can use the replaced 7.x manager, alongside the project's Spring Security 7 HTTP configuration APIs.

### 7.1. Why Supplier instead of retrieving Authentication upfront?

Accepting `Supplier<Authentication>` allows the framework to **defer** retrieving authentication until permission evaluation actually needs it. Custom code should not call `get()` multiple times unnecessarily; it can fetch once and use that value to compute the result. For `permitAll` or policies not needing a principal, the framework can avoid loading authentication unnecessarily.

### 7.2. Avoid narrowing the return type unnecessarily

In 7.x, declare manager results using the interface:

```java
AuthorizationResult result = manager.authorize(authSupplier, context);
if (result != null && result.isGranted()) {
    // Allow the next step, if other business conditions are met.
}
```

The snippet above uses variables already present in the project, not a standalone runnable program. Avoid casting `AuthorizationResult` to `AuthorizationDecision` if you do not control the concrete implementation.

## 8. Differences between implementer APIs and caller APIs

An easily overlooked change during upgrades is that the **call site** and **implementation site** do not change identically.

| Role in code | 6.3 | 6.4–6.5 | 7.x |
| --- | --- | --- | --- |
| **Implementing** a custom `AuthorizationManager` | Override `check` | Still must implement `check` per 6.x interface; `authorize` has default | Override `authorize` |
| **Caller** wanting the result | Call `check`, receive `AuthorizationDecision` | Prefer `authorize`, receive `AuthorizationResult` | Call `authorize`, receive `AuthorizationResult` |
| **Caller** wanting to enforce permission | Use `verify` or appropriate interceptor | Use `verify` or interceptor | Use `verify` or interceptor |
| **Reading status** | `isGranted()` | `isGranted()` | `isGranted()` |
| **Returning a simple result** | `new AuthorizationDecision(boolean)` | Same as before, compatible with `AuthorizationResult` | Same as before, compatible with `AuthorizationResult` |

### 8.1. Caller: 6.3 code vs. 6.5/7 code

**6.3:**

```java
// In a project that already has manager, authSupplier, context:
AuthorizationDecision decision = manager.check(authSupplier, context);
boolean allowed = decision != null && decision.isGranted();
```

**6.4, 6.5, and 7.x:**

```java
// In a project that already has manager, authSupplier, context:
AuthorizationResult result = manager.authorize(authSupplier, context);
boolean allowed = result != null && result.isGranted();
```

These are fragments illustrating API calls; they do not define variables or dependencies themselves. `allowed` here is the evaluation result **of that manager**; it does not guarantee passing every other check in the application.

### 8.2. Verify: use when "deny by exception" is needed

```java
// API available on AuthorizationManager:
manager.verify(authSupplier, context);
```

If denied, `verify` can throw `AccessDeniedException`; if allowed, the call completes normally. For a `null` result, read the version contract and specific checkpoint rules rather than assuming deny.

Use `verify` when a use case needs to turn a decision into a guard barrier. However, never **call `verify` and assume all resource permissions have been checked** if the manager only performs `hasAuthority("report:read")`. Tenant/owner/state constraints still belong in another policy.

### 8.3. Spring Security 7 and legacy APIs

`AuthorizationManager` is the modern model replacing older designs such as `AccessDecisionManager`/`AccessDecisionVoter`. In Spring Security 7, some older *Access API* components moved to the legacy `spring-security-access` module. Do not confuse **switching `check` to `authorize`** with **migrating the entire application from old voters/decision managers to `AuthorizationManager`**: those are two related but distinct migration axes.

If a project still uses `AccessDecisionVoter` or classic configurations, plan separately. This lesson teaches `AuthorizationManager` decisions and does not recommend new designs built on the legacy voter API.

## 9. Method security and decision results

### 9.1. @PreAuthorize is the common path

In many projects, there is no need to write `AuthorizationManager<MethodInvocation>` manually: use `@EnableMethodSecurity` and `@PreAuthorize` to express rules.

```java
// Fragment in a Spring-managed @Service; requires @EnableMethodSecurity.
@PreAuthorize("hasAuthority('report:read')")
public ReportView readReport(String reportId) {
    return reportService.load(reportId);
}
```

With the expression above, Spring Security uses internal authorization components to evaluate permissions when the method is called through the interceptor. You **do not need to manually construct** `AuthorizationDecision` inside the method. Do not think `@PreAuthorize` means "the Java method must return `AuthorizationResult`": the business method still returns `ReportView`.

### 9.2. Object-level policy

Example requiring both functional permission and reading a report for the right tenant/owner:

```java
@PreAuthorize("hasAuthority('report:read') and " +
        "@reportPolicy.canRead(authentication, #reportId)")
public ReportView readReport(String reportId) {
    return reportService.load(reportId);
}
```

The `reportPolicy` bean is implemented by the application: load the trusted report, check same tenant, sharing relationship, and state; `#reportId` requires the parameter name to be available at runtime (e.g. `-parameters` or an appropriate annotation mechanism). This is not syntax that grants access to all reports automatically.

### 9.3. When is a custom manager needed for methods?

Choose `AuthorizationManager<MethodInvocation>` when you need a complex shared mechanism, interceptor integration, invocation metadata, or policies inconvenient to express in SpEL. The method context type usually involves `MethodInvocation`, distinct from `RequestAuthorizationContext` for HTTP.

- Never take an `AuthorizationManager<RequestAuthorizationContext>` and cast it into a manager for `MethodInvocation`.
- Do not assume a method security interceptor automatically intercepts every call: self-invocation within the same bean can bypass the proxy.
- When both HTTP protection and method protection exist, both conditions that actually run must pass; they can be complementary rules, but must be documented and tested.

### 9.4. Returning dummy values on deny is not the default path

Normally, failing `@PreAuthorize` blocks the call with an exception; the method does not run. Newer Spring Security lines offer ways to customize how denied method invocations are handled, but do not assume all versions support the same annotations/handlers. When you simply want to **block access**, prefer clear rules instead of implementing fallbacks returning `null` or an "empty object" that might mask security errors.

## 10. Standalone Java 17 example to understand the result contract

The plain Java snippet below models a **result interface** and a **decision class** to illustrate the interface/implementation relationship. They are **not** real Spring classes; the program needs no framework dependencies and uses `Local...` names to avoid confusion. Real Spring code is in sections 6–7.

Create file `AuthorizationResultConceptDemo.java`:

```java
import java.util.Set;

public class AuthorizationResultConceptDemo {

    interface LocalAuthorizationResult {
        boolean isGranted();
    }

    record LocalAuthorizationDecision(boolean granted)
            implements LocalAuthorizationResult {

        @Override
        public boolean isGranted() {
            return granted;
        }
    }

    record Actor(String name, Set<String> permissions) {
        Actor {
            permissions = permissions == null
                    ? Set.of() : Set.copyOf(permissions);
        }
    }

    record Report(String id, String owner) {}

    static LocalAuthorizationResult authorize(Actor actor, Report report) {
        boolean allowed = actor != null
                && report != null
                && actor.name() != null
                && actor.permissions().contains("report:read")
                && actor.name().equals(report.owner());

        return new LocalAuthorizationDecision(allowed);
    }

    static String label(LocalAuthorizationResult result) {
        // The application deliberately fails closed on an undecided result.
        return result != null && result.isGranted() ? "ALLOW" : "DENY";
    }

    public static void main(String[] args) {
        Actor alice = new Actor(
                "alice", Set.of("report:read"));
        Actor bob = new Actor(
                "bob", Set.of("report:read"));
        Actor guest = new Actor(
                "guest", Set.of());
        Report report = new Report("r7", "alice");

        System.out.println("owner=" + label(authorize(alice, report)));
        System.out.println("same-permission-other-owner="
                + label(authorize(bob, report)));
        System.out.println("missing-permission="
                + label(authorize(guest, report)));
        System.out.println("missing-authentication="
                + label(authorize(null, report)));
        System.out.println("missing-resource="
                + label(authorize(alice, null)));
        System.out.println("abstain-fail-closed=" + label(null));

        LocalAuthorizationResult allowed = authorize(alice, report);
        System.out.println("result-interface=" + allowed.isGranted());
        System.out.println("decision-class="
                + allowed.getClass().getSimpleName());
    }
}
```

JDK 17+ commands:

```bash
javac AuthorizationResultConceptDemo.java
java AuthorizationResultConceptDemo
```

Stdout output:

```text
owner=ALLOW
same-permission-other-owner=DENY
missing-permission=DENY
missing-authentication=DENY
missing-resource=DENY
abstain-fail-closed=DENY
result-interface=true
decision-class=LocalAuthorizationDecision
```

**Analysis:**

1. The method's return type is the **interface** `LocalAuthorizationResult`, while at runtime it returns an instance of the **class/record** `LocalAuthorizationDecision`. This mirrors the relationship between `AuthorizationResult` and `AuthorizationDecision`.
2. Having the same `report:read` permission is not enough if Bob is not the resource owner. Authorization does not stop at constructing a boolean result.
3. `label(null)` returns `DENY` because this program **explicitly defines fail-closed behavior**. Do not assume this rule applies automatically to every Spring Security manager/interceptor.
4. In the real framework, `AuthorizationManager` also involves `Supplier<Authentication>`, the secure object, and HTTP/method interceptor lifecycles.

Creating mock classes with names matching package `org.springframework.security.authorization` to run without the library can mislead learners. Hence the example keeps the `Local` prefix, while real Spring samples in sections 6 and 7 are clearly marked as integration fragments.

## 11. Testing against the right version and contract

### 11.1. Directly testing a custom manager

For the 6.3–6.5 manager in section 6, expected test cases:

```text
Authentication with authority "report:read" -> granted = true
Authentication with only "report:write"      -> granted = false
Authentication with empty authorities          -> granted = false
Null Authentication / unauthenticated        -> must not ALLOW
```

In 6.3, use `manager.check(...).isGranted()`. In 6.4–6.5, prefer `manager.authorize(...).isGranted()` to practice the newer caller API. In 7.x, use `authorize(...)` only. This is a behavior comparison checklist, not a standalone test file.

**Crucially:** compile-test the source under the **exact BOM/version**, rather than testing behavior with Mockito alone. Mocking an old interface can hide that `@Override` is no longer valid on a newer version.

### 11.2. Real HTTP testing

An `AuthorizationDecision(true)` in a custom manager does not guarantee the final request returns `200 OK`. The request can still encounter CSRF, business validation, tenant checks, controllers, exception handlers, or other security components. Therefore:

- Test a valid request with `report:read` and a resource the test user is permitted to view.
- Test without `report:read`, trying both the same route and another route.
- Test an endpoint without a matcher falling under `anyRequest().denyAll()`.
- Test distinguishing `401`/`403`/login redirect per authentication entry point configuration.
- Test `@PreAuthorize` via calls on a Spring-proxied bean.
- Test object authorization: having the permission but wrong owner/tenant must still be blocked.
- For state-changing requests, supply a valid CSRF token if required by the application so CSRF rejections are not confused with manager logic.

### 11.3. Testing "null" and exceptions

Write tests for custom managers whenever code allows `null`. Check **consumer behavior**: when a manager abstains, does another manager handle it, does the route have a deny fallback, and is the request ever allowed unintentionally? Never merely assert `result == null` and assume it is safe.

With `verify`, verify an exception is thrown on a **negative decision**, and test that a positive decision completes normally. Never catch `AccessDeniedException` and continue writing data if the business action mandates permission.

### 11.4. Testing a 6.5 → 7.x upgrade

1. Upgrade versions via a unified BOM/parent POM; inspect the resolved dependency tree/versions.
2. Compile **custom `AuthorizationManager` implementers** first: migrate `check` to `authorize` with the proper return type.
3. Find all callers of `manager.check(...)` and switch to `authorize(...)` using `AuthorizationResult`.
4. Review custom adapters, method interceptors, event publishers, or loggers expecting `AuthorizationDecision` instead of `AuthorizationResult`.
5. Remove unnecessary `(AuthorizationDecision) result` casts.
6. Test across HTTP, method security, and async/batch/message flows if the project uses them.
7. Verify role/authority mappings, caches, and object policies preserve behavior.
8. Test `ALLOW`, `DENY`, and missing-data/abstain cases before deploying.

Renaming the method is part of migration, but **does not guarantee semantic equivalence** if the old manager relied on `null`, custom combination rules, or different exception handling. Integration tests remain decisive.

## 12. Common mistakes when learning and implementing

| Mistake | Why it is wrong | Correct approach |
| --- | --- | --- |
| "Since AuthorizationResult appeared in 6.3, 6.3 uses authorize(...)" | Confuses when the interface was added with when the method was added | 6.3 uses `check`; `authorize` starts in 6.4 |
| "AuthorizationDecision was replaced and cannot be used in 7.x" | The class still implements `AuthorizationResult` | Use `new AuthorizationDecision(boolean)` as an implementation |
| "In 6.5, overriding authorize alone is enough" | `check` is still an abstract method in the 6.5 API | Implement `check` or use a version-appropriate adapter |
| "In 7.x, keep @Override check" | `check` was removed from the interface | Override `authorize` |
| "authorize always returns AuthorizationDecision" | Contract returns `AuthorizationResult` | Use `isGranted()`, never cast unconditionally |
| "null means DENY" | `null` represents abstain; depends on consumer | Return explicit decisions; fail closed deliberately |
| "new AuthorizationDecision(false) returns HTTP 403 by itself" | Decision does not write HTTP responses directly | Enforcement point handles denial/exceptions |
| "verify is just an alias returning boolean" | `verify` checks and throws an exception when denied | Use `authorize` to get a result; `verify` when needing a guard |
| "An HTTP manager works verbatim for methods" | Generic type `T` differs | Pick `RequestAuthorizationContext` or `MethodInvocation` appropriately |
| "Having the permission lets you read any resource" | Missing object-level check | Combine tenant/owner/ACL/state |
| "Code from 'current' examples runs on an older BOM" | APIs differ by version | Check resolved version/corresponding Javadoc, compile-test |
| "Null pointer from unauthenticated caller -> catch Exception and allow" | Accidentally fails open | Block, preserve authentication flow, or return safe deny |

## 13. Self-check questions

**Q1.** How do `AuthorizationDecision` and `AuthorizationResult` differ?

**Answer:** `AuthorizationResult` is an interface describing grant status; `AuthorizationDecision` is a concrete class implementing that interface with a boolean constructor. Both provide `isGranted()`.

**Q2.** A module uses Spring Security 6.3. A developer calls `manager.authorize(...)` and the build reports no such method. Why?

**Answer:** `AuthorizationManager.authorize(...)` was added in 6.4. For 6.3, use `check(...)` or plan a dependency upgrade.

**Q3.** In Spring Security 6.5, a custom manager only overrides `authorize(...)` without implementing `check(...)`. Why might it fail to compile?

**Answer:** `check(...)` is still the abstract method on the 6.5 interface (even though deprecated). `authorize(...)` is a default method. You must satisfy the contract of the interface you compile against.

**Q4.** In Spring Security 7, why does `@Override` on `check(...)` fail?

**Answer:** `check(...)` was removed from `AuthorizationManager`. You need to implement `authorize(...)` with the 7.x signature and return type.

**Q5.** `AuthorizationResult result = manager.authorize(...)`. Should you cast `result` to `AuthorizationDecision` to call `isGranted()`?

**Answer:** No. The interface already exposes `isGranted()`. Casting adds an unnecessary coupling and can fail with other implementations.

**Q6.** A manager returns `null`. Can you conclude the request is guaranteed to be denied?

**Answer:** No. `null` means undecided/abstain. Behavior depends on the consumer/combinator; secure applications should enforce explicit fail-closed rules and test them.

**Q7.** A custom HTTP manager returns `ALLOW` for `report:read`. Is the caller automatically allowed to read another tenant's report?

**Answer:** No. Tenant/membership/owner/ACL checks under object-level authorization are still required. Functional permissions do not replace those conditions.

**Q8.** When should you use `verify` instead of `authorize`?

**Answer:** When the call site needs a guard that throws `AccessDeniedException` on a deny decision. When you want the result to display/log/test/compose policies, use the version-appropriate `authorize` while still handling `null` and additional permissions properly.

## 14. Project application checklist

- [ ] Read the **resolved Spring Security version** from the dependency tree/BOM; do not guess from Spring Boot or Java version.
- [ ] Document which API line is used: 6.3 `check`; 6.4–6.5 `authorize` for callers while `check` remains in implementations; 7.x `authorize` for both.
- [ ] Type results using the `AuthorizationResult` interface when supported by the API; use `AuthorizationDecision` to construct simple decisions.
- [ ] Never cast results unconditionally; never assume `null` is a framework-wide default allow or deny.
- [ ] Enforce `deny by default` and verify sufficient object/tenant/context conditions.
- [ ] Match custom managers to the exact context type `T` and the proper HTTP/method enforcement point.
- [ ] Enable method security if needed; test proxies/self-invocation and non-HTTP call paths.
- [ ] Test code against the exact dependency before upgrading; cover allow, deny, abstain, exceptions, and real requests.
- [ ] Track API changes during migrations and avoid mixing 6.x and 7.x docs.

**Conclusion:** `AuthorizationDecision` is a **way to construct a result**, `AuthorizationResult` is the **contract for reading a result**, and `AuthorizationManager` is **where the decision is made**. Spring Security 6.3 uses `check`; 6.4–6.5 transitions callers toward `authorize` while keeping `check` deprecated; 7.x completes the transition. Choosing the version-appropriate API, returning explicit decisions, and testing enforcement are essential for an authorization flow that is both accurate and maintainable.

## References — verify against exact version

- Spring Security 6.3.3 API — `AuthorizationManager` (`check`): https://docs.spring.io/spring-security/site/docs/6.3.3/api/org/springframework/security/authorization/AuthorizationManager.html
- Spring Security 6.5 API — `AuthorizationManager` (`check` deprecated, `authorize`): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html
- Spring Security 7.0 API — `AuthorizationManager` (`authorize`): https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/authorization/AuthorizationManager.html
- Spring Security 6.5 API — `AuthorizationResult`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationResult.html
- Spring Security 7.0 API — `AuthorizationDecision`: https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/authorization/AuthorizationDecision.html
- Spring Security 7.0 — Authorization architecture: https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/architecture.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — HTTP Requests Authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
