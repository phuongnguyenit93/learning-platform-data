# Implementing check or authorize According to the Version Contract

## 1. Goal: Right Runtime API, Right Security Decision

`AuthorizationManager<T>` is the Spring Security contract used to decide **whether to allow an action on a protected object of type `T`**. The framework can invoke a manager at an HTTP request, a method invocation, or other integration points.

When implementing an `AuthorizationManager`, you cannot just remember a method name from an online example. Between **Spring Security 6.3**, **6.4–6.5**, and **7.x**, the contract changed:

- In 6.3, the method to implement is `check(...)`, returning `AuthorizationDecision`.
- In 6.4–6.5, `authorize(...)` was added and recommended, yet `check(...)` remains an abstract method in the interface so classes directly implementing the interface still must implement `check(...)`.
- Starting in 7.0, `check(...)` is removed from the interface; `authorize(...)` is the abstract method to implement, returning `AuthorizationResult`. The `Supplier` type also has a wildcard and nullability annotations to watch for when writing `@Override`.

Therefore, what you must determine **before writing code** is the exact `spring-security-core` version on the compile classpath of the **module being built**; then read the Javadoc for **that exact version**.

A correct implementation must satisfy two criteria simultaneously:

1. **Correct Java/API contract:** signature, generic `T`, return type, and `@Override` compile cleanly and are invoked by the interceptor.
2. **Correct authorization contract:** ALLOW only with sufficient proof; DENY when permissions are insufficient; `null`/abstain and exceptions must be handled explicitly to avoid accidental fail-open behavior.

This lesson is about **version contracts and implementation**, not upgrading all of Spring Boot or designing every ACL policy.

## 2. Version Matrix to Remember

| Spring Security | Abstract method of `AuthorizationManager<T>` | Remaining methods | Decision return type | What to write |
|---|---|---|---|---|
| 6.3.x | `check(Supplier<Authentication>, T)` | `verify(...)` is default | `AuthorizationDecision` or `null` | `@Override check(...)` |
| 6.4.x | `check(Supplier<Authentication>, T)`, deprecated | `authorize(Supplier<Authentication>, T)` is default; `verify(...)` is default | `check`: `AuthorizationDecision`; `authorize`: `AuthorizationResult` | Direct implementing classes **still must** provide `check(...)` |
| 6.5.x | `check(Supplier<Authentication>, T)`, deprecated | `authorize(...)` is default; `verify(...)` is default | Same as 6.4 | Keep adapter for 6.x; prepare to migrate to `authorize` |
| 7.0.x / 7.1.x | `authorize(Supplier<? extends Authentication>, T)` | `verify(...)` is default; `check` no longer in interface | `AuthorizationResult` or `null` | `@Override authorize(...)` with matching signature |

In 7.x Javadoc, type-use nullability is expressed explicitly, e.g., `Supplier<? extends @Nullable Authentication>`. Code does not need to import a separate nullable annotation just to illustrate Java generics, but the **`? extends` part of the signature must match** when overriding. `AuthorizationDecision` still implements `AuthorizationResult`, so `new AuthorizationDecision(true/false)` can be used as the result in newer versions.

**Scope note:** these milestones belong to Spring Security APIs, not "Spring Boot 3 automatically supports authorize." Boot uses dependency management to pick a Spring Security version; an application may override that version. Always check the actual dependency rather than guessing from a starter name.

Version-specific reference docs:
- [AuthorizationManager 6.3.3 Javadoc](https://docs.spring.io/spring-security/site/docs/6.3.3/api/org/springframework/security/authorization/AuthorizationManager.html).
- [AuthorizationManager 6.4.10 Javadoc](https://docs.spring.io/spring-security/site/docs/6.4.10/api/org/springframework/security/authorization/AuthorizationManager.html).
- [AuthorizationManager 6.5.11 Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html).
- [AuthorizationManager 7.0 Javadoc](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/authorization/AuthorizationManager.html).

## 3. Clear View of the Three Methods: check, authorize, and verify

### 3.1. check: the legacy contract, still present in 6.4–6.5

In version 6.3, the basic shape:

~~~java
public interface AuthorizationManager<T> {
    AuthorizationDecision check(
            Supplier<Authentication> authentication,
            T object);

    default void verify(
            Supplier<Authentication> authentication,
            T object) {
        // Framework implementation.
    }
}
~~~

This is an **abbreviated description** of the interface for learning the contract, not the full library source code. `check` takes `Supplier<Authentication>` and a protected object of type `T`. The result can be `AuthorizationDecision(true)`, `AuthorizationDecision(false)`, or `null` to decline making a decision (*abstain*).

In 6.4/6.5, `check` is marked deprecated, yet remains a mandatory part of the interface for directly implementing classes. "Deprecated" means you should plan to migrate in future designs, **not that an existing class automatically becomes an implementation needing only `authorize`**.

### 3.2. authorize: the new contract

Starting in 6.4, `authorize(...)` returning `AuthorizationResult` was added; in 6.4–6.5 it is a default method. Starting in 7.0, it is the **abstract method**, and `check` is removed from the interface.

Concise shape of the 7.x API:

~~~java
public interface AuthorizationManager<T> {
    AuthorizationResult authorize(
            Supplier<? extends Authentication> authentication,
            T object);

    default void verify(
            Supplier<? extends Authentication> authentication,
            T object) {
        // Framework implementation.
    }
}
~~~

This is also a simplified model for reading; the real Javadoc includes nullable annotations on the relevant types. Because `AuthorizationDecision implements AuthorizationResult`, the following code is valid once the newer version's signature matches:

~~~java
return new AuthorizationDecision(granted);
~~~

Having `AuthorizationResult` as the return type lets the framework and other implementations supply richer decision metadata in the future without forcing clients onto one concrete class.

### 3.3. verify: convenience method, not the primary override target

`verify(supplier, object)` is a default method. It uses the manager's result to enforce the check, **throwing `AccessDeniedException` when receiving a negative decision**. When a manager returns `null`, that is *abstain*, not an automatic DENY; **do not assume `verify(...)` will throw an exception on null**.

Do not call `verify` directly and ignore other components without understanding abstain semantics and how managers are composed. If a use case requires a positive decision, write the manager to always return an explicit ALLOW/DENY instead of `null`.

## 4. Correct Example for Spring Security 6.3

Suppose we need a manager taking `T = String`, where the object is the required authority name, such as `"document:read"`. The manager must deny when there is no valid authentication, the authority is blank, or the principal is anonymous.

File `RequiredAuthorityManager.java` (a Spring Security 6.3 integration class; the project must have the Spring Security dependency):

~~~java
import java.util.function.Supplier;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;

public final class RequiredAuthorityManager
        implements AuthorizationManager<String> {

    @Override
    public AuthorizationDecision check(
            Supplier<Authentication> authentication,
            String requiredAuthority) {

        if (requiredAuthority == null || requiredAuthority.isBlank()) {
            return new AuthorizationDecision(false);
        }

        Authentication current = authentication.get();
        if (current == null
                || !current.isAuthenticated()
                || current instanceof AnonymousAuthenticationToken) {
            return new AuthorizationDecision(false);
        }

        boolean granted = current.getAuthorities().stream()
                .anyMatch(authority ->
                        requiredAuthority.equals(authority.getAuthority()));

        return new AuthorizationDecision(granted);
    }
}
~~~

**Why does this code match the 6.3 contract?**

- Uses `check(Supplier<Authentication>, String)` directly with `@Override`.
- `AuthorizationDecision` is the interface's return type.
- The second parameter type matches `AuthorizationManager<String>`.
- Does not return null for missing data; returns an explicit denial decision.
- Does not implicitly use `hasRole`: compares the authority **literally**, e.g., `document:read` differs from `ROLE_document:read`.

This is an example of **functional permission checking**, not permission on a specific document. To check tenant/owner/ACL, use the appropriate context and resource policy instead of comparing an authority alone.

**Do not** copy a 7.x snippet using `@Override authorize(...)` into code compiled against 6.3: the 6.3 interface lacks that method, causing an `@Override` error and a missing abstract `check` error.

## 5. Spring Security 6.4–6.5: "authorize Is Recommended" Does Not Mean Dropping check

In 6.4–6.5, the Javadoc simultaneously shows:

~~~text
@Deprecated AuthorizationDecision check(Supplier<Authentication>, T) // abstract
default AuthorizationResult authorize(Supplier<Authentication>, T)
default void verify(Supplier<Authentication>, T)
~~~

Because `check` is still abstract, a class that writes **only**:

~~~java
@Override
public AuthorizationResult authorize(
        Supplier<Authentication> authentication,
        String requiredAuthority) {
    return new AuthorizationDecision(true);
}
~~~

is **not a complete implementation** of `AuthorizationManager<String>` in 6.4/6.5; the compiler still requires `check(...)`. That snippet also grants access unconditionally; it is only used to illustrate the signature error and **must not be used in production**.

One way to write for 6.4/6.5 source is to keep the `check(...)` implementation as in section 4. The default `authorize(...)` in that Spring Security version delegates to the existing implementation. If you want to implement `authorize(...)` yourself to center decision logic on the new API, you still must supply a `check(...)` adapter:

~~~java
import java.util.function.Supplier;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.core.Authentication;

public final class DenyMissingAuthorityManager
        implements AuthorizationManager<String> {

    @Override
    public AuthorizationResult authorize(
            Supplier<Authentication> authentication,
            String requiredAuthority) {

        Authentication current = authentication.get();
        boolean granted = requiredAuthority != null
                && !requiredAuthority.isBlank()
                && current != null
                && current.isAuthenticated()
                && current.getAuthorities().stream()
                        .anyMatch(a -> requiredAuthority.equals(a.getAuthority()));
        return new AuthorizationDecision(granted);
    }

    @Override
    @Deprecated
    public AuthorizationDecision check(
            Supplier<Authentication> authentication,
            String requiredAuthority) {

        AuthorizationResult result =
                authorize(authentication, requiredAuthority);
        return new AuthorizationDecision(
                result != null && result.isGranted());
    }
}
~~~

This is **6.4/6.5 integration code**, depending on the Spring Security library, not a standalone Java program. Security-wise, this class returns DENY if `authorize` yields null. In real code, extract the policy logic into a shared helper method to avoid recursion or redundant evaluation; the adapter must forward **one way only**. For example, `authorize → check` and `check → authorize` simultaneously would cause infinite recursion.

Note: the 6.4/6.5 snippet uses `isAuthenticated()`, yet `AnonymousAuthenticationToken` can have the authenticated flag set; for private endpoints, use proper anonymous/remember-me evaluation as in section 4 and application policy. This must not be treated as per-record permission.

**When to choose which approach?**

- Module targets only 6.3: implement `check`.
- Module pinned to 6.4/6.5: still implement `check`; optionally expose `authorize` if logic requires it and tests cover it.
- Module moves completely to 7: remove the `check` adapter and implement `authorize` with the 7 signature.
- If a codebase must build against two major versions, do not assume a single source class can override both; split implementations by source set/build profile or use an internal adapter built and tested separately per version. Do not force a compiled artifact against a different ABI without verifying compatibility.

## 6. Correct Example for Spring Security 7.x

In Spring Security 7, the Javadoc only has `authorize(...)` and `verify(...)`. When implementing the interface directly, pay attention to the supplier wildcard type:

~~~java
import java.util.function.Supplier;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.core.Authentication;

public final class RequiredAuthorityManager
        implements AuthorizationManager<String> {

    @Override
    public AuthorizationResult authorize(
            Supplier<? extends Authentication> authentication,
            String requiredAuthority) {

        if (requiredAuthority == null || requiredAuthority.isBlank()) {
            return new AuthorizationDecision(false);
        }

        Authentication current = authentication.get();
        if (current == null
                || !current.isAuthenticated()
                || current instanceof AnonymousAuthenticationToken) {
            return new AuthorizationDecision(false);
        }

        boolean granted = current.getAuthorities().stream()
                .anyMatch(authority ->
                        requiredAuthority.equals(authority.getAuthority()));

        return new AuthorizationDecision(granted);
    }
}
~~~

**Differences compared to 6.3:**

- The method is `authorize`, not `check`.
- The return type is declared as `AuthorizationResult`.
- The supplier is declared as `Supplier<? extends Authentication>`, matching the 7.x contract wildcard (the Javadoc also shows nullable type-use annotations).
- No need to implement `check`, and do not place `@Override` on such a method because the 7 interface no longer defines it.
- `AuthorizationDecision` remains a valid concrete result because it implements `AuthorizationResult`.

A confusing error commonly seen when upgrading to 7.x: keeping the 6.4/6.5 signature `authorize(Supplier<Authentication>, T)`, adding `@Override`, and hitting a **name clash / neither overrides** error because the generic wildcards differ despite identical JVM erasure. Do not delete `@Override` "just to make it compile"; fix the signature to match the Javadoc on your compile classpath.

Furthermore, the example above intentionally denies when authority or authentication is missing. Do not let `null` substitute for DENY, because callers may interpret null as abstain.

## 7. Why Do Many Lambdas Stay Compatible While Override Classes Break?

A functional interface can be implemented with a lambda. Because a lambda does not explicitly name `check` or `authorize`, the same source shape:

~~~java
AuthorizationManager<String> denyMissing =
        (authentication, requiredAuthority) -> {
            Authentication current = authentication.get();
            boolean granted = current != null
                    && requiredAuthority != null
                    && current.getAuthorities().stream()
                           .anyMatch(a -> requiredAuthority.equals(a.getAuthority()));
            return new AuthorizationDecision(granted);
        };
~~~

can compile after **rebuilding against each version** because the compiler binds the lambda to the corresponding abstract method. That does not mean binaries compiled against an older version are guaranteed compatible at a newer runtime; always rebuild and run actual tests.

This is an illustrative lambda snippet in a project with these imports:

~~~java
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
~~~

In production code, add anonymous checks, tenant scoping, and object permissions; the simple lambda here only illustrates functional interface syntax. When policies grow complex, a named class with clear tests is easier to maintain.

**Important note:** the `AuthorizationManager<String>` created in the example does not automatically become a Spring Security rule. You must **attach the manager to an interceptor/DSL** at the proper pointcut or request rule; merely declaring an `AuthorizationManager` bean does not ensure every request/method invokes it.

## 8. Object Type T and Integration Point Must Match

`T` in `AuthorizationManager<T>` is not always a domain resource. It is **the secure object context passed in by the interceptor**.

| Context | Example type `T` | Data needed |
|---|---|---|
| HTTP servlet request | `RequestAuthorizationContext` | `HttpServletRequest`, path variables, and context data |
| Method security before invocation | `MethodInvocation` | Method signature and arguments |
| Method security after invocation | `MethodInvocationResult` (depends on version/mechanism) | Invocation together with return value |
| Custom policy contract | `DocumentAccessRequest` or `String` | Resource ID, tenant, verified authority |
| Message authorization | Corresponding message context type of the integration | Message, headers, and trusted actor |

The generic `String` manager in sections 4–7 is an interface-teaching example; it **cannot be passed directly** to `authorizeHttpRequests().access(...)`, which requires a manager for the appropriate HTTP context.

### 8.1. Example Attaching a Manager to HTTP (General Applicability)

If a request requires authority `report:read`, Spring Security already has built-in `hasAuthority(...)`; a custom manager is only needed when extra custom policy is required.

Servlet integration code illustrating a manager with explicit deny decisions:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.security.core.Authentication;

@Configuration
class ReportSecurityConfig {

    @Bean
    SecurityFilterChain reportFilterChain(HttpSecurity http)
            throws Exception {

        AuthorizationManager<RequestAuthorizationContext> reportPolicy =
                (authentication, context) -> {
                    Authentication current = authentication.get();
                    boolean granted = current != null
                            && current.isAuthenticated()
                            && current.getAuthorities().stream()
                                    .anyMatch(a ->
                                            a.getAuthority().equals("report:read"));
                    return new AuthorizationDecision(granted);
                };

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/reports/**").access(reportPolicy)
                .anyRequest().denyAll());

        return http.build();
    }
}
~~~

This is an **HTTP configuration example**, not a standalone `javac` program; it requires Spring Security, Boot, or an application configuring filters, beans, and an HTTP runtime. The rule only illustrates the wiring path and does not replace tenant/row-level authorization checks. Real applications must account for other `SecurityFilterChain`s, actuator, static assets, CORS, CSRF, sessions, anonymous access, authentication entry points, and matcher ordering.

For simplicity and accuracy with a plain single authority, prefer writing:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/reports/**").hasAuthority("report:read")
    .anyRequest().denyAll());
~~~

**Do not use `permitAll` or `anyRequest().authenticated()` in place of a specific permission rule** when an endpoint requires a specific authority.

### 8.2. Method Invocation Needs a Properly Attached Interceptor

A manager for method security can be declared as `AuthorizationManager<MethodInvocation>`. However, merely making it a bean does not guarantee method interception. To intercept methods, you must register a pointcut/interceptor using the version's corresponding configuration API or use `@PreAuthorize` on the service. Often a cleaner approach is delegating policy to a bean:

~~~java
@PreAuthorize("@documentPolicy.canRead(authentication, #id)")
public DocumentView findDocument(long id) {
    return queryService.findDocument(id);
}
~~~

`documentPolicy` is an application bean with a clear boolean contract; the logic in this bean should check tenant/resource too. This snippet is an **integration example** illustrating that sometimes you do not need to write an `AuthorizationManager` yourself; method security must be enabled and calls must pass through a Spring proxy.

If you do write a custom manager for method interception, distinguish **before invocation** from **after invocation**; the context types differ and post-invocation checks on writes may occur after side effects.

## 9. ALLOW / DENY / ABSTAIN Decisions: Avoid Confusing null with deny

Spring Security allows implementations to return `null` to indicate **no decision** (*abstain*). This is not `AuthorizationDecision(false)`.

| Return value from manager | `isGranted()` | Logical meaning | Typical `verify` outcome |
|---|---|---|---|
| `new AuthorizationDecision(true)` | `true` | ALLOW | Does not throw since there is no negative decision |
| `new AuthorizationDecision(false)` | `false` | DENY | Throws `AccessDeniedException` |
| `null` | No object to call | ABSTAIN | Does not automatically throw like DENY |
| Exception inside policy | No normal decision | Evaluation / dependency error | Propagates/handled per stack, never treated as ALLOW |

**When a single manager protects a sensitive operation, return an explicit true/false**. Do not return null merely because the principal is missing, the token lacks a tenant, or an ACL service timed out.

Example:

~~~java
AuthorizationDecision decision =
        new AuthorizationDecision(permissionVerified && resourceVisible);
~~~

Both booleans here **must** be computed from trusted sources with nulls/exceptions handled and proper scoping. If the permission service fails, choose fail-closed behavior and report an appropriate error; never let the request through because a decision "could not be reached."

### Why Is Abstain Dangerous When Composing?

Certain compositions have special semantics. For instance, `AuthorizationManagers.allOf(...)` with abstaining managers may treat abstain as non-blocking, and default variants may grant if all managers abstain. Never assume "allOf + null = deny."

Since Spring Security 6.3, an overload exists for the default when all abstain:

~~~java
AuthorizationManager<RequestAuthorizationContext> policy =
        AuthorizationManagers.allOf(
                new AuthorizationDecision(false),
                primaryManager,
                secondaryManager);
~~~

This is an **illustrative integration snippet**; `primaryManager`/`secondaryManager` must share the same generic context and exist. The overload using `AuthorizationDecision(false)` defines **all-abstain → DENY**, though it will not fix a policy if another manager branch grants too broadly. Test individual manager semantics and fallback ordering.

For mandatory resource rules (tenant/owner), that check should **return DENY** when unverified, avoiding returning null and letting another rule grant access unexpectedly.

## 10. Supplier<Authentication>: Lazy, Not Self-Authenticating Trust

`Supplier<Authentication>` is passed into the manager to defer fetching authentication until actually needed. A public endpoint using `permitAll` may never need to touch the context. In a custom manager:

1. Check conditions that do not require authentication first (e.g., whether the required authority name is present).
2. Call `authentication.get()` only when a user-based decision is needed.
3. Consider storing the result in a local variable; avoid calling the supplier repeatedly or retaining the supplier for later asynchronous use.
4. For HTTP contexts, never treat client-sent paths/queries/headers as verified identity.
5. Do not assume `Authentication.isAuthenticated()` alone excludes anonymous users; use `AuthenticationTrustResolver` or built-in managers that handle anonymous/remember-me accurately.

Common Java logic example:

~~~java
Authentication principal = authentication.get();
if (principal == null) {
    return new AuthorizationDecision(false);
}
~~~

This is only a fragment and insufficient on its own: an anonymous Authentication can still have `principal != null`. Define policies explicitly for anonymous access and scopes.

**Do not hold results in a global cache** if decisions depend on user/tenant/request. If decisions are cached, key them by actor, authority, resource, policy version, and an appropriate revocation mechanism.

## 11. Common Compile Errors and How to Diagnose Causes

| Compiler error / symptom | Possible cause | How to verify / fix |
|---|---|---|
| "Class is not abstract and does not override abstract method check(...)" | Source is 6.4/6.5 but only implements `authorize` | Check the Javadoc being compiled against; implement mandatory `check` or upgrade cleanly to 7 |
| "Method does not override method from its superclass" on `authorize` | Compiling against 6.3 where the interface lacks `authorize` | Use `check` with the 6.3 signature |
| "Method does not override …" on `check` | Compiling against 7 where `check` was removed | Switch to `authorize` |
| "Name clash: same erasure, yet neither overrides" | 7.x uses `Supplier<Authentication>` instead of the API wildcard | Check 7.x generic Javadoc; use `Supplier<? extends Authentication>` |
| "Incompatible types: AuthorizationResult cannot be converted to AuthorizationDecision" | Using the new `authorize` result with an old-typed variable | Use `AuthorizationResult` and `isGranted()`; do not cast unless you control the implementation |
| Deprecation warning on check | Spring Security 6.4/6.5 | Do not remove the abstract method just to silence the warning; plan a verified migration |
| Implementation compiles, but rule does not run | Manager not wired into HTTP DSL/interceptor; Spring proxy bypassed | Check real configuration, invoke via Spring bean, and run integration tests |
| "Cannot resolve symbol AuthorizationResult" | Compile classpath too old or mismatched dependencies | Verify exact artifact versions; avoid copying newer snippets into older codebases |
| Runtime `NoSuchMethodError` / `AbstractMethodError` | Runtime Spring Security bytecode/libraries mismatch compile version, or incompatible extension | Print runtime dependency tree, rebuild extensions against target version, do not patch with reflection |

**Avoid dangerous workarounds:** do not remove `@Override` to hide errors, do not add an uninvoked overloaded method, and do not catch all exceptions and return `new AuthorizationDecision(true)`. The compiler is pointing out a **contract mismatch** that must be resolved in dependencies and signatures.

## 12. Identify the Exact Actual Dependency Before Fixing

When building with Gradle, suggested commands (run for the exact multi-project module, adjusting configuration names per module):

~~~bash
./gradlew :your-module:dependencyInsight --dependency spring-security-core --configuration compileClasspath
./gradlew :your-module:dependencyInsight --dependency spring-security-core --configuration runtimeClasspath
~~~

With Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.security
~~~

These are **example commands**, not stdout. `:your-module` is a placeholder and must be replaced with the actual module. On Windows, `gradlew.bat` can be used. Compare versions of `spring-security-core`, `spring-security-config`, `spring-security-web`, and test dependencies; avoid mixing incompatible major/minor versions.

You can also use your IDE's "Go to declaration" on `AuthorizationManager` to inspect the actual interface on the compile classpath. Then open the **matching version's** Javadoc and verify:

- Is the current abstract method `check` or `authorize`?
- Is the `Supplier` type `Supplier<Authentication>` or `Supplier<? extends Authentication>`?
- Is the return type `AuthorizationDecision` or `AuthorizationResult`?
- What default methods exist? Are there `@Nullable` annotations?
- How does `verify` handle negative/null; what are composition semantics if using `allOf/anyOf`?
- Which framework version do tests run against? Are any extension libraries compiled against older versions?

When using the Spring Boot BOM, avoid pinning individual spring-security artifacts to different versions without a verified reason. When upgrading major versions, read the migration guide and update all interface touchpoints systematically.

## 13. Upgrading Safely from check to authorize

An auditable migration path:

1. **Freeze current contracts.** Record compile/runtime versions, every `AuthorizationManager<T>` implementation, all `check/authorize/verify` call sites, and manager compositions.
2. **Decouple decision logic from version adapters.** Write a plain Java policy or domain service receiving trusted actor/resource inputs and returning an explicit `ALLOW/DENY` result.
3. **Keep 6.x adapters accurate.** On 6.4/6.5, `check` is still abstract; if implementing `authorize`, keep a valid `check` adapter. Avoid bidirectional forwarding loops.
4. **Update signatures when moving to 7.** Implement `authorize(Supplier<? extends Authentication>, T)`, return `AuthorizationResult`, and remove `@Override check` methods no longer on the interface.
5. **Review null semantics.** Ensure null/abstain is never treated as DENY in one place and ALLOW in another; configure default-deny on composed managers if required by policy.
6. **Build per target version.** For shared libraries, test bytecode separately per major version; never infer compatibility solely from IDE compilation against one version.
7. **Run real integration tests.** HTTP/method interceptors must invoke the new implementation; test DENY, ALLOW, null, anonymous, missing tenant, dependency failures, proxy bypass, `verify` behavior, and middleware handling.
8. **Monitor after upgrade.** Track denied/abstained/error metrics, latency, and permitted request paths; never log tokens or sensitive ACL data.

If the codebase only supports a single version, do not add unnecessary compatibility layers. Use the exact API of your running version and remove obsolete adapters once fully migrated to 7.

## 14. Standalone Java 17 Demo: Distinguishing DENY from ABSTAIN

To grasp the semantics without a Spring runtime, let us simulate a manager returning one of three states. This is a **plain Java program**, not a full simulation of Spring's `AuthorizationManager.verify`.

Create `DecisionDemo.java`:

~~~java
public class DecisionDemo {
    enum Decision { ALLOW, DENY, ABSTAIN }

    static Decision decide(String actor, String authority, boolean dataReady) {
        if (actor == null || authority == null) {
            return Decision.DENY;
        }
        if (!dataReady) {
            return Decision.ABSTAIN;
        }
        return actor.equals("an") && authority.equals("document:read")
                ? Decision.ALLOW
                : Decision.DENY;
    }

    static boolean failClosed(Decision result) {
        return result == Decision.ALLOW;
    }

    public static void main(String[] args) {
        Decision allowed = decide("an", "document:read", true);
        Decision denied = decide("binh", "document:read", true);
        Decision unknown = decide("an", "document:read", false);

        System.out.println("allowed=" + allowed
                + ", permit=" + failClosed(allowed));
        System.out.println("denied=" + denied
                + ", permit=" + failClosed(denied));
        System.out.println("unknown=" + unknown
                + ", permit=" + failClosed(unknown));
    }
}
~~~

Run on Java 17 or later:

~~~bash
javac DecisionDemo.java
java DecisionDemo
~~~

Stdout:

~~~text
allowed=ALLOW, permit=true
denied=DENY, permit=false
unknown=ABSTAIN, permit=false
~~~

In the demo, the `failClosed` adapter permits only on ALLOW. **In real Spring, `null` from a manager means abstain with semantics determined by the caller/composition**, so never use this simulation to claim `verify` always denies on null. If required authorization attributes are unavailable, a complete manager should return `AuthorizationDecision(false)` or throw a controlled technical error rather than returning null on a required protected path.

## 15. Necessary Unit Tests and Integration Tests

### 15.1. Contract Unit Tests per Version

For **6.3**:

~~~java
AuthorizationDecision decision =
        manager.check(() -> authenticatedUser, "document:read");

assertThat(decision).isNotNull();
assertThat(decision.isGranted()).isTrue();
~~~

For **6.4–6.5**, both `check` and `authorize` can be tested:

~~~java
AuthorizationDecision legacy =
        manager.check(() -> authenticatedUser, "document:read");
AuthorizationResult modern =
        manager.authorize(() -> authenticatedUser, "document:read");

assertThat(legacy.isGranted()).isEqualTo(modern.isGranted());
~~~

For **7.x**:

~~~java
AuthorizationResult result =
        manager.authorize(() -> authenticatedUser, "document:read");

assertThat(result).isNotNull();
assertThat(result.isGranted()).isTrue();
~~~

These three snippets are **illustrative test snippets** depending on `manager`/`authenticatedUser` fixtures, JUnit, and an assertion library; they are not standalone Java 17 classes. For denied/absent authentication, expect an explicit negative decision. If intentionally supporting abstain, add caller/composition tests reflecting real abstain semantics.

### 15.2. Testing verify, null, and Composition

Prove that:

- `verify` with a negative decision throws `AccessDeniedException`.
- `verify` with a positive decision does not throw.
- `verify` with an abstaining manager is not assumed to behave as DENY unless the framework explicitly does so.
- `AuthorizationManagers.allOf` when all components abstain: verify the chosen default; consider the all-abstain DENY overload.
- `AuthorizationManagers.anyOf` when managers grant, deny, or abstain: verify the actual combined rule so one manager cannot grant too broadly.
- Null authentication, anonymous tokens, and remember-me per security policy must never grant unintended access.

Summary test example (pseudo-fixture on Spring Security, not a standalone class):

~~~java
assertThatThrownBy(
        () -> manager.verify(() -> userWithoutAuthority, "document:read"))
        .isInstanceOf(AccessDeniedException.class);
~~~

### 15.3. Test the Real Interceptor, Not Just Direct Manager Calls

A unit test calling `manager.check(...)` or `authorize(...)` can PASS even when the manager is **not registered** with Spring Security. Integration tests are also required:

1. Does the HTTP request match the custom `.access(manager)` rule according to matcher order?
2. Which `SecurityFilterChain` is handling the request? Multiple chains can route to different rules.
3. Is method security enabled and the interceptor attached to the right method?
4. Do calls pass through the Spring-managed proxy rather than `this.method()` self-invocation?
5. Does the actual context object match the generic `T`?
6. When no rule matches, is there a `denyAll()` fallback or appropriate policy?
7. A user with the right role but wrong tenant/owner must be blocked even if a general authority-checking manager grants access.
8. When the permission backend times out or returns incomplete data, operations must not be allowed due to null/exceptions.
9. For non-HTTP paths (messages, schedulers), are proper adapters/policies enforced rather than relying on HTTP rules?
10. After version upgrades, run tests on the real runtime to catch `AbstractMethodError`, `NoSuchMethodError`, generic bridge issues, or mixed-version artifacts.

## 16. Characteristic Security Bugs from Implementing the Contract Wrong

**Bug A — Replacing null with `true` to avoid "false blocks."** That is fail-open. Clarify why the manager abstains and grant only when the policy genuinely allows.

**Bug B — Returning negative but having caller logic ignore the result.** For instance, calling `manager.authorize(...)` only to log and proceeding with the update anyway. Let the interceptor enforce the result, or explicitly check and block when not granted.

**Bug C — Using `verify` expecting mandatory deny on all nulls.** Default `verify` only throws on negative decisions; abstain can slip through. If undecided must deny, return an explicit negative decision or compose with an all-abstain default-deny overload.

**Bug D — Implementing the class with the right API without attaching it to a pointcut/filter chain.** The manager has no effect on requests/methods if the framework never calls it.

**Bug E — Passing the wrong type `T`.** A manager for `String` cannot express permissions on `RequestAuthorizationContext` or `MethodInvocation`; casting does not bridge semantic differences.

**Bug F — Trusting `authentication.get() != null` as sufficient.** Anonymous tokens can still exist, roles can be missing, and tenant claims must be verified.

**Bug G — Forgetting resource policy.** The `document:read` authority is not enough for a document belonging to another tenant.

**Bug H — Catching policy exceptions and granting access.** A permission backend outage becomes a bypass path; fail closed and report the error.

**Bug I — Updating the method signature to a newer example without upgrading all dependencies.** Compilation or runtime may resolve a different API; inspect `dependencyInsight` and test the ABI.

**Bug J — Using `@Override check` on 7.x or `@Override authorize` on 6.3.** Choose the contract matching your version instead of deleting annotations to hide mismatches.

## 17. Pre-Merge Checklist

- [ ] Verified the exact compile/runtime `spring-security-core` version of the module.
- [ ] Checked the matching version Javadoc and corresponding abstract method signature.
- [ ] `@Override` genuinely overrides with no bridge/name-clash issues from `Supplier` generics.
- [ ] Return type is right, using `AuthorizationDecision`/`AuthorizationResult` per contract.
- [ ] ALLOW/DENY/ABSTAIN are clearly defined; null is never equated with false or true.
- [ ] When permission is required, missing data, anonymous users, or permission backend errors never grant access.
- [ ] `verify` and manager compositions have tests for positive, negative, and abstain outcomes.
- [ ] Type `T` matches the secure context passed by the HTTP/method/message interceptor.
- [ ] Manager is wired into the right `SecurityFilterChain`, interceptor, or policy use case.
- [ ] Authority, tenant, and resource permissions are checked within a trusted scope.
- [ ] Both policy unit tests and real interceptor/route integration tests exist, including critical non-HTTP paths.
- [ ] Clean build on the target version, with no mismatched Spring Security artifacts or runtime linkage errors.

**Final rule:** Getting the method name right only makes the code compile. A proper `AuthorizationManager` makes trustworthy decisions, handles abstain deliberately, and is invoked by Spring Security at the right boundary. For 6.3, implement `check`; for 6.4–6.5, remember `check` is still abstract even though deprecated; for 7.x, implement `authorize` with the new signature and return type.

## Version-Specific References

- [Spring Security 6.3.3 API – AuthorizationManager](https://docs.spring.io/spring-security/site/docs/6.3.3/api/org/springframework/security/authorization/AuthorizationManager.html)
- [Spring Security 6.4.10 API – AuthorizationManager](https://docs.spring.io/spring-security/site/docs/6.4.10/api/org/springframework/security/authorization/AuthorizationManager.html)
- [Spring Security 6.5 API – AuthorizationManager](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html)
- [Spring Security 7.0 API – AuthorizationManager](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/authorization/AuthorizationManager.html)
- [Spring Security 7.0 What's New – check removed](https://docs.spring.io/spring-security/reference/7.0-SNAPSHOT/whats-new.html)
- [Spring Security Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
