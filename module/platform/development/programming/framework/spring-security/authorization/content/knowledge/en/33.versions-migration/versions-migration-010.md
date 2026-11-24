# Support for @AuthorizeReturnObject, Denial Handling, and Annotation Templates

## 1. Three Capabilities to Distinguish When Upgrading Spring Security

When upgrading Spring Security versions, code can **compile without properly protecting data**, or conversely fail to compile because a feature does not exist in the resolved dependency. The three mechanisms in this topic address three distinct problems in *method authorization*:

1. **`@AuthorizeReturnObject`**: wraps the object returned by a method in a proxy that applies method security advice. A getter/operation on the returned object annotated with `@PreAuthorize` or `@PostAuthorize` is checked when invoked through that proxy.
2. **`@HandleAuthorizationDenied` + `MethodAuthorizationDeniedHandler`**: defines how to handle method authorization **denials**. It can throw an exception as usual or return a safe value—such as `null`, a redacted value, or a fallback object—if the API contract allows it.
3. **Annotation templates**: create meta-annotations like `@RequiresPermission("profile:read")` to reuse `@PreAuthorize("hasAuthority('{value}')")`. Templates require corresponding configuration infrastructure, not merely a standard Java annotation.

All three operate in systems with `@EnableMethodSecurity` and Spring AOP. They complement one another, yet do not replace **per-resource/tenant** checks, do not replace the HTTP filter chain, and do not automatically guarantee DTO/JSON serialization or other data access paths are safe.

Running example: user `alice` holds `profile:read` and is permitted to read her own profile ID 1. Profile ID 2 belongs to `bob`. The `email` field on profile 1 may be read only if Alice also holds `profile:email`. When that permission is missing, a protected getter returns `null` per the illustrative fallback policy; querying profile 2 still returns `null` before any object is exposed.

Expected learning outcomes: identify the exact **supporting versions**, choose pre/post method check placement, know when return-object proxies operate, avoid using fallbacks to mask serious authorization failures, and write tests proving permissions are actually enforced after upgrading.

## 2. Capability Matrix by Version: Do Not Infer from Spring Boot

The milestones below come from official API documentation and method security guides. When targeting a specific version, check documentation for **that exact branch** and your resolved dependencies rather than assuming the "current" doc page matches your project environment.

| Capability | Spring Security 6.2 and Earlier | 6.3.x | 6.4+ / 6.5 and Newer Lines with Corresponding APIs |
| --- | --- | --- | --- |
| `@EnableMethodSecurity`, `@PreAuthorize`, `@PostAuthorize` | Present in Spring Security 6 generation; requires enabling method security | Present | Present |
| `@AuthorizeReturnObject` | Not available | **Introduced in 6.3** | Present |
| `@HandleAuthorizationDenied` | Not available | **Introduced in 6.3** | Present |
| `MethodAuthorizationDeniedHandler` | Not available | **Introduced in 6.3** | Present |
| `AnnotationTemplateExpressionDefaults` and `'{value}'` placeholders | Not available | Not available in 6.3 | **Introduced in 6.4**, used with configuration bean |
| Protecting returned getters via proxy | Requires another strategy/manual authorization | Available with proper configuration and version | Available; verify proxy and AOT compatibility as needed |

**Mandatory security note when selecting 6.3.x:** Spring published **CVE-2024-38810** regarding missing partial method security advice on objects proxied via `@AuthorizeReturnObject`/`AuthorizationAdvisorProxyFactory` in certain AOP + FactoryBean configurations. Versions **6.3.0 and 6.3.1** are affected under the advisory's conditions; **6.3.2** is the fix on the 6.3 branch. Therefore, do not choose 6.3.0/6.3.1 for this feature; use a supported branch and appropriate patch. Do not infer that every app using `@AuthorizeReturnObject` was affected: the advisory specifies exact conditions.

Spring Boot manages Spring Security versions via its BOM/dependency management. **The Boot version is not the Security version.** Verify that `spring-security-core`, `spring-security-config`, and `spring-security-test` resolve consistently. With Gradle, you can inspect from the proper module:

```bash
./gradlew dependencyInsight --dependency spring-security-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-config --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-test --configuration testRuntimeClasspath
```

On Windows, use `gradlew.bat`. In multi-project Gradle builds, you may need `:module-name:dependencyInsight` and the plugin's exact configuration. These commands are inspection instructions, **not measured dependency output of the current module**.

When locating APIs in JARs or your IDE, keep these package names in mind:

- `org.springframework.security.authorization.method.AuthorizeReturnObject`
- `org.springframework.security.authorization.method.HandleAuthorizationDenied`
- `org.springframework.security.authorization.method.MethodAuthorizationDeniedHandler`
- `org.springframework.security.core.annotation.AnnotationTemplateExpressionDefaults`

Do not fix a "cannot find symbol" error by creating a custom annotation with the same name or copying code across versions. Verify dependency versions, security patches, and support scope.

## 3. Method Security Mechanics: Before, After, and on Returned Objects

`@EnableMethodSecurity` registers supported interceptors for method calls via Spring AOP. Conceptually:

```text
Spring bean proxy
   │
   ├─ @PreAuthorize: evaluated before method executes
   │      └─ DENY → throws error by default; handler can alter result
   │
   ├─ method body (data read, computation, side effects...)
   │
   ├─ @PostAuthorize: evaluated against returnObject after method runs
   │      └─ DENY → throws error by default; handler can process result
   │
   └─ @AuthorizeReturnObject: wraps returned object in a proxy
          ├─ getDisplayName() → may have no separate restriction
          └─ getEmail()       → @PreAuthorize on getter
                                 └─ DENY → @HandleAuthorizationDenied
```

Exact advisor ordering can be affected by configuration/custom interceptors; this diagram conveys practical semantics and **does not represent every advisor chain in every application**.

### @PreAuthorize and @PostAuthorize are not equivalent

- `@PreAuthorize` denies **before the body runs**, suitable for actions with side effects such as deletes, fund transfers, privilege grants, or database writes. Expressions can rely on authorities, method parameters, or policy beans.
- `@PostAuthorize` evaluates **after the body has run** and can inspect `returnObject`. Useful for read-only methods when decisions depend on the returned object; however, if the body already wrote data or published events before denial, a subsequent exception does not automatically revert side effects in all environments.
- `@AuthorizeReturnObject` applies security advice to the object after it is returned. It **does not automatically assign** permissions to any getter, nor turn fields into `REDACTED`. Getters/nested methods need appropriate annotations or policy services.
- `@HandleAuthorizationDenied` changes behavior upon denial; it **does not alter ALLOW/DENY conditions**. Fallbacks can hide from callers that access was denied; choose them deliberately.

Good tests distinguish: whether the main method was blocked, whether the returned object is genuinely proxied, which getter was denied, whether the body ran prior to denial, and whether the final output leaks sensitive data.

## 4. @AuthorizeReturnObject: When Should You Use It?

Suppose `ProfileView` has two getters: `getDisplayName()` is allowed for anyone permitted to access the profile, while `getEmail()` is restricted to callers with `profile:email`. After the service returns `ProfileView` from an `@AuthorizeReturnObject` method, invoking `profile.getEmail()` on the **returned proxy** passes through method security.

```java
// Illustrates annotation placement; full example is in Section 7.
@AuthorizeReturnObject
public ProfileView profileById(long id) {
    return repository.findVisible(id, currentUser());
}

public class ProfileView {
    @PreAuthorize("hasAuthority('profile:email')")
    public String getEmail() {
        return email;
    }
}
```

Observe these important limitations:

1. Returning an object from a service **without** `@AuthorizeReturnObject` leaves a plain object whose getters execute without interceptors.
2. Marking `@AuthorizeReturnObject` when getters lack `@PreAuthorize`/`@PostAuthorize` or matching policies **creates no field protection rules**.
3. Calling a getter **inside the original object** via `this.getEmail()` bypasses the returned-object proxy, so do not rely on it as the sole guard inside domain logic.
4. Methods on a Spring bean can bypass the proxy when invoked via `this.otherMethod()` (*self-invocation*); design clear bean/policy boundaries.
5. `final` classes/records/methods, interface/JDK proxies, objects inside collections/`Optional`, serialization, and native images have specific proxy constraints; test on **actual** return types rather than assuming every Java object proxies cleanly.
6. Never use `@AuthorizeReturnObject` as a substitute for tenant/owner-scoped queries. If the service already returned an unauthorized object, data can leak via other getters, logs, serializers, mappers, or non-proxied paths.

### Class-level scope

`@AuthorizeReturnObject` can be placed at the type level, applying to methods of that type. However, Spring Security will attempt to proxy many return types, including `String`, `Integer`, or collections of value types. The official guide suggests a `TargetVisitor` to skip value types in such setups:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.authorization.method
        .AuthorizationAdvisorProxyFactory.TargetVisitor;

@Bean
static TargetVisitor skipValueTypes() {
    return TargetVisitor.defaultsSkipValueTypes();
}
```

This is a **fragment inside a `@Configuration` class** and requires a version supporting that API. In applications with only a few methods returning domain objects, placing the annotation directly on **specific methods** is usually easier to control.

## 5. Handling Denials with @HandleAuthorizationDenied

The default behavior of a denied method is throwing `AuthorizationDeniedException`/`AccessDeniedException` per the active security layer. Web apps may map that exception to HTTP 403 in the right context; a service call from a background job or unit test observes the exception directly. There is no rule that every denial automatically yields HTTP 403 when no HTTP request exists.

When an optional field is not viewable, contracts sometimes require `"email": null` or `"email": "***"`. Spring Security provides `@HandleAuthorizationDenied(handlerClass = ...)` to specify a `MethodAuthorizationDeniedHandler` implementation.

Two callbacks to distinguish:

| Callback | When Applicable | Has Original Body Result? | Best Suited For |
| --- | --- | --- | --- |
| `handleDeniedInvocation(MethodInvocation, AuthorizationResult)` | Denied before method executes; general callback for denied invocations | No return value from the blocked body | Returning `null`, a fixed placeholder, or rethrowing |
| `handleDeniedInvocationResult(MethodInvocationResult, AuthorizationResult)` | When denial can occur after the method produces a result | Method result is available | Partially masking a produced value under a very specific policy |

By default, `handleDeniedInvocationResult` delegates to `handleDeniedInvocation`. If a handler **inspects the original data** to mask after `@PostAuthorize`, ensure the outcome is always safe and the raw value never leaks into logs/errors/caches. For write operations, **never use a fallback to pretend success**. Normally deny explicitly before side effects.

### Why not return null everywhere?

- For nullable, non-essential fields, `null` can be a reasonable contract if clients understand its meaning.
- For methods returning primitive `int`/`boolean` or `@NonNull` contracts, `null` breaks type contracts or causes runtime errors.
- For endpoints exporting sensitive data, falling back to an empty list can hide missing permissions, produce inaccurate reports, or cause logic bugs.
- For mutations, returning `"SUCCESS"` when actually denied misleads callers and can corrupt audit trails.
- For APIs distinguishing "not found" from "forbidden," design responses to avoid enumeration leaks while matching security policy.

Test **both allow and deny**, verifying the method body does not execute when `@PreAuthorize` denies, the response contains no raw values, and testing full response serialization rather than only direct Java getter assertions.

## 6. Annotation Templates: Reusing Policies with Meta-Annotations

A fixed meta-annotation works like:

```java
@Target({ ElementType.TYPE, ElementType.METHOD })
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize("hasRole('ADMIN')")
public @interface AdminOnly {}
```

In versions supporting templates (since **6.4**), replace the fixed value with an annotation parameter:

```java
@Target({ ElementType.TYPE, ElementType.METHOD })
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize("hasAuthority('{value}')")
public @interface RequiresPermission {
    String value();
}
```

`@RequiresPermission("profile:read")` resolves via the template to an expression equivalent to `hasAuthority('profile:read')`. The value in `{value}` is an annotation attribute declared in source code; it is **not** a string pulled from an HTTP body to execute SpEL.

A configuration bean is required:

```java
@Bean
static AnnotationTemplateExpressionDefaults templateDefaults() {
    return new AnnotationTemplateExpressionDefaults();
}
```

Import `org.springframework.security.core.annotation.AnnotationTemplateExpressionDefaults` and place the fragment inside a `@Configuration` class. Do not confuse having a Java meta-annotation with Spring Security **having template expansion enabled**: without the bean or the right version, placeholders may fail to resolve.

Rules when defining annotation templates:

- Use proper quotes in SpEL, e.g., `hasAuthority('{value}')`. Test resolved expressions; templates with malformed role/permission strings cause mass denials or unintended conditions.
- Annotation values should be developer-controlled, never concatenating user input into SpEL. For policies depending on request IDs/tenants, call a policy bean with validated parameters instead of building dynamic templates.
- `hasAuthority("profile:read")` checks the authority string directly; `hasRole("ADMIN")` normally uses the `ROLE_` prefix. Tests must supply the exact authorities granted in `Authentication`.
- Repeating `@PreAuthorize` twice on the same method **is not supported**. Do not stack a meta-annotation containing `@PreAuthorize` alongside another `@PreAuthorize` on a method expecting Spring to combine them safely; use one combined expression or policy bean.
- Templates may target types/methods per `@Target`, but check inherited annotations on classes/interfaces and conflict cases. Never assume conflicting annotations from multiple interfaces have a natural precedence order.
- `AnnotationTemplateExpressionDefaults#setIgnoreUnknown(false)` can catch unknown placeholders in strict configurations; the API defaults to ignoring unrecognized placeholders. Before changing this behavior, test all existing template expressions.

Annotation templates cut repetition and policy typos, yet **do not automatically generate** object-level checks. An ID-reading method still needs actor/tenant constraints in its query or domain policy.

## 7. Spring Security 6.4+ Integration Example with All Three Features

The example below sits in a Java 17+ application with Spring Security 6.4 or later, matching Spring Framework/Spring Test, and `spring-security-test` for testing. It uses an in-memory repository to focus on method security; it **does not replace** database/tenant checks in production. Files share package `demo.security`.

### 7.1. Configuration: enabling method security, templates, and denied handler

File `MethodSecuritySetup.java`:

```java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.annotation.AnnotationTemplateExpressionDefaults;

@Configuration
@EnableMethodSecurity
public class MethodSecuritySetup {
    @Bean
    static AnnotationTemplateExpressionDefaults templateDefaults() {
        return new AnnotationTemplateExpressionDefaults();
    }

    @Bean
    NullDeniedHandler nullDeniedHandler() {
        return new NullDeniedHandler();
    }
}
```

File `NullDeniedHandler.java`:

```java
package demo.security;

import org.aopalliance.intercept.MethodInvocation;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.authorization.method.MethodAuthorizationDeniedHandler;

public class NullDeniedHandler implements MethodAuthorizationDeniedHandler {
    @Override
    public Object handleDeniedInvocation(
            MethodInvocation invocation, AuthorizationResult result) {
        return null;
    }
}
```

Here the handler is strictly for a getter returning a nullable `String`. If reusing a shared handler across APIs returning other objects or primitives, handle types explicitly to avoid errors or accidentally masking denials.

### 7.2. Parameterized meta-annotation

File `RequiresPermission.java`:

```java
package demo.security;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.security.access.prepost.PreAuthorize;

@Target({ ElementType.TYPE, ElementType.METHOD })
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize("hasAuthority('{value}')")
public @interface RequiresPermission {
    String value();
}
```

`@RequiresPermission("profile:read")` on the service below controls functional permission. If tests show the method is not blocked despite lacking `profile:read`, check the template bean, dependency versions, and Spring AOP proxying before assuming the expression itself is right.

### 7.3. Domain object with a sensitive getter

File `ProfileView.java`:

```java
package demo.security;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authorization.method.HandleAuthorizationDenied;

public class ProfileView {
    private final long id;
    private final String owner;
    private final String displayName;
    private final String email;

    public ProfileView(
            long id, String owner, String displayName, String email) {
        this.id = id;
        this.owner = owner;
        this.displayName = displayName;
        this.email = email;
    }

    public long getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public boolean ownedBy(String actor) {
        return owner.equals(actor);
    }

    @PreAuthorize("hasAuthority('profile:email')")
    @HandleAuthorizationDenied(handlerClass = NullDeniedHandler.class)
    public String getEmail() {
        return email;
    }
}
```

`ProfileView` is a regular non-`final` class with non-`final` getters so it can be checked via class-based proxying in this illustrative setup. Omitting `getOwner()` is intentional so `owner` is not exposed directly via serializers; production should use projections/DTOs containing only needed fields.

### 7.4. Repository enforcing per-object permissions

File `ProfileStore.java`:

```java
package demo.security;

import java.util.Map;
import org.springframework.stereotype.Repository;

@Repository
public class ProfileStore {
    private final Map<Long, ProfileView> values = Map.of(
            1L, new ProfileView(
                    1L, "alice", "Alice", "alice@example.test"),
            2L, new ProfileView(
                    2L, "bob", "Bob", "bob@example.test"));

    public ProfileView findVisible(long id, String actor) {
        ProfileView result = values.get(id);
        return result != null && result.ownedBy(actor)
                ? result : null;
    }
}
```

The security invariant here is **returning only objects owned by the actor**. In a real database, enforce that constraint in a safe query scoped by owner/tenant/ACL across every access path. Never rely solely on `getEmail()` to protect object 2.

### 7.5. Service applying annotation template and protecting the return object

File `ProfileService.java`:

```java
package demo.security;

import org.springframework.security.authorization.method.AuthorizeReturnObject;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class ProfileService {
    private final ProfileStore store;

    public ProfileService(ProfileStore store) {
        this.store = store;
    }

    @RequiresPermission("profile:read")
    @AuthorizeReturnObject
    public ProfileView getProfile(long id) {
        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();
        return store.findVisible(id, auth.getName());
    }
}
```

With `profile:read` and matching ownership, the method returns a wrapped `ProfileView` so `getEmail()` can be denied or allowed. For actors not permitted to read the object, the service returns `null`. The actor comes from Spring Security's context, never a client-supplied owner string.

**This example requires Spring Security 6.4+**, because `AnnotationTemplateExpressionDefaults` was introduced in that version. When running on 6.3.2, you can keep `@AuthorizeReturnObject` and `@HandleAuthorizationDenied`, but must replace `@RequiresPermission` with `@PreAuthorize("hasAuthority('profile:read')")` or a **fixed** meta-annotation without template placeholders.

## 8. Testing Spring Method Security: Verifying Real Proxies and Denials

JUnit 5 example using Spring Test + Spring Security Test; four standalone tests in package `demo.security`.

File `ProfileServiceSecurityTest.java`:

```java
package demo.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(classes = {
        MethodSecuritySetup.class,
        ProfileStore.class,
        ProfileService.class
})
class ProfileServiceSecurityTest {
    @Autowired ProfileService service;

    @Test
    @WithMockUser(username = "alice", authorities = "profile:read")
    void returnsPublicFieldsButMasksDeniedEmail() {
        ProfileView profile = service.getProfile(1L);

        assertNotNull(profile);
        assertEquals("Alice", profile.getDisplayName());
        assertNull(profile.getEmail());
    }

    @Test
    @WithMockUser(
            username = "alice",
            authorities = { "profile:read", "profile:email" }
    )
    void returnsEmailWhenFieldPermissionExists() {
        ProfileView profile = service.getProfile(1L);

        assertNotNull(profile);
        assertEquals("alice@example.test", profile.getEmail());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "other")
    void deniesServiceWithoutFunctionalPermission() {
        assertThrows(AccessDeniedException.class,
                () -> service.getProfile(1L));
    }

    @Test
    @WithMockUser(
            username = "alice",
            authorities = { "profile:read", "profile:email" }
    )
    void deniesForeignProfileBeforeReturningObject() {
        assertNull(service.getProfile(2L));
    }
}
```

These assertions verify three layers in exact order: the meta-annotation enforces permission on the service, `@AuthorizeReturnObject` causes `getEmail()` to be checked, and `@HandleAuthorizationDenied` turns a denied getter into `null`. If `@AuthorizeReturnObject` is removed from the service and the first test receives the raw email, we immediately catch the gap from an unproxied getter. If the template bean is missing so `@RequiresPermission` fails to resolve, the allow/deny tests catch it.

The Java snippets above are **integration code requiring Spring dependencies**; they cannot be compiled with plain `javac`. Run them through your project build, for example:

```bash
./gradlew test --tests demo.security.ProfileServiceSecurityTest
```

In multi-project builds, use the right module's task and `spring-security-test` dependency. Direct service tests do not replace HTTP/Jackson, session, or non-proxied path tests. Add an integration test invoking real endpoints/serialization if objects are rendered to JSON.

**Do not rely on a single fixed exception type when testing systems with custom exception translators.** `assertThrows(AccessDeniedException.class)` fits the service call in this example. Over HTTP, the mapping may be 403 or a custom error format depending on controller/advice.

## 9. Standalone Java 17 Example to Verify ALLOW, DENY, and Fallback Logic

This snippet does not use Spring AOP: it simulates logic to show clearly that service permission, object permission, and field permission are three distinct conditions. It runs standalone on JDK 17 to cross-check expected outcomes before writing integration tests.

File `AuthorizationFeatureDemo.java`:

```java
import java.util.Set;

public class AuthorizationFeatureDemo {
    record Actor(String name, Set<String> authorities) {}
    record Profile(String owner, String label, String email) {}

    static Profile view(Actor actor, Profile profile) {
        if (!actor.authorities().contains("profile:read")) {
            throw new SecurityException("profile:read denied");
        }
        return actor.name().equals(profile.owner()) ? profile : null;
    }

    static String visibleEmail(Actor actor, Profile profile) {
        Profile allowed = view(actor, profile);
        return allowed != null
                && actor.authorities().contains("profile:email")
                ? allowed.email()
                : null;
    }

    public static void main(String[] args) {
        Profile own = new Profile(
                "alice", "Alice", "alice@example.test");
        Profile foreign = new Profile(
                "bob", "Bob", "bob@example.test");
        Actor basic = new Actor(
                "alice", Set.of("profile:read"));
        Actor elevated = new Actor(
                "alice", Set.of("profile:read", "profile:email"));

        System.out.println("ownReadable=" + (view(basic, own) != null));
        System.out.println("foreignReadable=" +
                (view(basic, foreign) != null));
        System.out.println("emailBasic=" + visibleEmail(basic, own));
        System.out.println("emailElevated=" +
                visibleEmail(elevated, own));
    }
}
```

Compile and run:

```bash
javac AuthorizationFeatureDemo.java
java AuthorizationFeatureDemo
```

Exact stdout:

```text
ownReadable=true
foreignReadable=false
emailBasic=null
emailElevated=alice@example.test
```

In plain Java, `visibleEmail` returns `null` via a conditional expression. In Spring Security, `@HandleAuthorizationDenied` is invoked when an annotation denies on a **proxy**, not because Java masks fields automatically. Both models illustrate the same policy, though their execution mechanisms differ.

## 10. Post-Result Handling: Masking and Side-Effect Risks

`@PostAuthorize` can inspect `returnObject` after a getter/service has run. Upon denial, a handler can receive `MethodInvocationResult` and return a masked value. Principle example (fragment for an appropriate handler):

```java
@Override
public Object handleDeniedInvocationResult(
        MethodInvocationResult invocationResult,
        AuthorizationResult decision) {
    // For unauthorized fields, never return the raw value to callers.
    return "[REDACTED]";
}
```

Import `MethodInvocationResult` from `org.springframework.security.authorization.method`. When adding this callback to `MethodAuthorizationDeniedHandler`, still implement `handleDeniedInvocation(...)` per the interface for pre-body denials. Avoid casts like `(String) invocationResult.getResult()` if results can be null or change types without tests.

Distinguish two styles:

```java
// Pre-body: never read sensitive data when lacking permission.
@PreAuthorize("hasAuthority('secret:read')")
@HandleAuthorizationDenied(handlerClass = NullDeniedHandler.class)
public String readSecret() {
    return secretStore.load();
}

// Post-body: checks only after result exists; suitable only when policy
// allows loading first before masking, with zero side effects.
@PostAuthorize("hasAuthority('secret:read')")
@HandleAuthorizationDenied(handlerClass = RedactDeniedHandler.class)
public String readForDisplay() {
    return secretStore.load();
}
```

`RedactDeniedHandler` in the second example is an **illustrative name** for a handler matching the fragment above; this snippet is not a standalone program. For data requiring "must not even be fetched from the database without permission," enforce permissions **before the query** and restrict data in the query itself rather than post-processing. For writes/edits/deletes, check before the body, add transactions and DB predicates; masking after execution does not undo writes.

### Policy against side-channel data leaks

A handler might return `null` yet log `returnObject`, emit stack traces containing an email, or publish an event carrying sensitive data before denial. Reviews must inspect HTTP bodies, logs, caches, tracing, metrics, and side effects alike. Never pass raw results into denied-access audit records without explicit justification and controls.

## 11. Return Type Compatibility, AOT, and Serializers

### 11.1. Optional, List, nested objects

Official documentation shows examples with `Optional<User>` and `List<Account>` alongside `@AuthorizeReturnObject`. Element-proxying behavior depends on version and return type; test **the exact return shapes** in your app: `ProfileView`, `Optional<ProfileView>`, `List<ProfileView>`, arrays, subclasses, or nested objects. Never extrapolate from a single-object return method to every collection/custom wrapper.

On a proxied class, every sensitive getter needs an explicit policy, including getters on nested objects. If `getProfile()` returns `ProfileView` while `getAddress()` returns an `Address` holding confidential fields, decide whether to proxy `Address` as well, use a whitelisted DTO, or enforce a dedicated policy service.

### 11.2. Classes, final, records, primitives

Class-based proxies hit limitations when a class or method is `final`; JDK interface proxies follow different invocation rules. Java `record`s are `final` by default, so never equate "is a DTO record" with "can be class-proxied like a standard bean." For value types and strings, consider `TargetVisitor.defaultsSkipValueTypes()` when using class-level annotations.

Check Spring AOP configuration (class vs. interface proxying) and where serializers read getters. A serialization framework reading fields directly or a mapper holding the unwrapped target can bypass method security advice; **restrict fetched and exposed fields directly at the repository/projection** whenever security matters.

### 11.3. AOT/native image and generics

During ahead-of-time compilation, Spring Security must know which types contain secured methods or require proxying. Spring Security provides runtime-hint registrars for return types, such as `AuthorizeReturnObjectHintsRegistrar` and `PrePostAuthorizeExpressionBeanHintsRegistrar`, when generic type erasure hides element types from method signatures.

If your application uses native images, test real collection types, proxy classes, nested types, reflection, and hint registration. Do not infer native-image compatibility solely from passing JVM tests. Registrar API names and registration mechanisms can change across lines, so verify documentation for your exact version before copying config fragments.

### 11.4. Execution overhead

Adding proxies and checking multiple getters can increase permission decisions, DB reads, or policy service calls. For large list responses, avoid N+1 permission queries; push object-level filters into database queries, batch-check permissions safely, and cache by actor/tenant/scope with proper invalidation and expiry. Optimize only after proving policies do not leak.

## 12. Differences Across 6.2 → 6.3 → 6.4+ Upgrades and Migration Path

### Step 1 — Inspect baseline and existing permissions

Read `build.gradle`/BOM, resolved dependency outputs, `@EnableMethodSecurity` or `@EnableGlobalMethodSecurity` settings, `@PreAuthorize`/`@PostAuthorize` policies, custom expression handlers, and service return types. Record baseline behavior: who can read what, who is denied, and HTTP/log side effects.

**Another critical migration detail:** `@EnableGlobalMethodSecurity(prePostEnabled = true)` is the legacy configuration. `@EnableMethodSecurity` enables pre/post by default and uses the `AuthorizationManager` API. If previously only `@Secured` was enabled with pre/post off, consider `prePostEnabled = false` during migration instead of accidentally activating dormant annotations.

### Step 2 — Select the right version and patch

- **Apps on 6.2 and below:** cannot adopt `@AuthorizeReturnObject`/`@HandleAuthorizationDenied` as in 6.3, and lack 6.4 annotation templates. Consider explicit service-layer policies, projections/DTOs, and a controlled upgrade.
- **Apps on 6.3:** use return-object proxies and denied handlers per 6.3 APIs; **avoid 6.3.0–6.3.1** due to the advisory noted above, checking at least 6.3.2 and appropriate patches. Parameterized `{value}` templates require 6.4+.
- **Apps on 6.4+ or newer lines:** can enable the template bean and keep return-object/denied-handler features with regression tests. Verify exact packages, AOT/proxy behavior, and security semantics on your branch.
- Do not upgrade `spring-security-core` alone while `spring-security-config` and test dependencies remain on another minor outside supported dependency management. The Spring ecosystem requires alignment to prevent version skew.

### Step 3 — Migrate sequentially by behavior

1. Lock down tests for functional permissions, object permissions, and sensitive fields before changing annotations.
2. Upgrade dependencies and follow the official migration guide; confirm method security is actually enabled and proxies are being created.
3. Apply `@AuthorizeReturnObject` to one domain/view with simple sensitive getters, test allow/deny, then expand incrementally.
4. Use `@HandleAuthorizationDenied` only when the API contract wants a fallback; clearly test `null`/masked/error differences. Never mechanically "turn every 403 into null."
5. On 6.4+, create template meta-annotations alongside the config bean, testing exact authorities, role prefixes, parameters, and denial when unauthorized.
6. For collections/nested types/records/native images, write dedicated tests for real shapes before rolling out broadly.
7. Monitor logs/audits and compare post-deployment responses: zero raw field leaks, no unintended HTTP contract shifts, and no unacceptable N+1 growth.
8. Keep deployment rollback ready per project operations if security regressions surface; treat deny policies as the standard baseline.

Never rely on a single "all logged-in requests return 200" test to declare migration complete. Tests must include missing-permission and non-owner object cases.

## 13. Practical Regression Test Matrix

| Scenario | Test Action | Expectation |
| --- | --- | --- |
| `@EnableMethodSecurity` not enabled | Invoke annotated method | Test must detect guard did not run; configuration error |
| Missing `profile:read` | `service.getProfile(1)` | Denied before body, no object returned |
| Has `profile:read`, own profile | `service.getProfile(1)` | Returns proxied object; regular getters work |
| Has `profile:read` but lacks `profile:email` | Invoke `proxy.getEmail()` | `null` per sample handler, no raw email |
| Has both authorities | Invoke `proxy.getEmail()` | Returns actor's exact email |
| Attempts to fetch another user's profile | `service.getProfile(2)` | `null`/denied per domain, no secret values exposed |
| `@AuthorizeReturnObject` removed in negative check | Invoke sensitive getter | Test detects getter policy is no longer applied |
| `@AuthorizeReturnObject` on class with value returns | Check proxy/visitor | No unexpected proxy failure on `String`/final types |
| Template used without bean or wrong version | Use `@RequiresPermission` | Test detects annotation fails to enforce properly |
| Duplicate/conflicting annotations | Start context / call method | Startup/test detects ambiguous configuration |
| Denied with `@PostAuthorize` | Read-only method with return value | Handler masks data; no leaks via errors/logs |
| Denied before mutation | Data-writing method | Zero DB updates, events, or false success audits |
| `Optional/List/nested` | Access each element/getter | Policy operates across every data path |
| HTTP serialization | Serialize object to JSON | No sensitive fields exposed via direct field access |
| AOT/native image | Native integration test | Proxies, interceptors, hints, and results are accurate |
| AOP + FactoryBean config | Check advisory-affected branch | Use patched version; test method advice executes |

The most important tests must **fail if a guard is removed**. For return-object proxies, compare raw objects directly against proxied objects; for annotation templates, temporarily remove the template bean in an isolated test to prove tests actually catch lost enforcement. Security tests are proof of runtime execution, not merely reflection checks for annotation presence.

## 14. Misconceptions That Cause Bugs During Version Upgrades

- **"Every 6.x release has `@AuthorizeReturnObject`."** The API starts in 6.3; 6.2 and earlier lack it.
- **"Being on 6.3 means `{value}` templates work."** `AnnotationTemplateExpressionDefaults` starts in 6.4.
- **"`@AuthorizeReturnObject` protects every field by itself."** Getters/methods still need rules; pre-proxy access paths must also be safe.
- **"Protecting getters removes the need for object/tenant checks."** Cross-tenant objects can leak through other fields or serializers.
- **"`@HandleAuthorizationDenied` decides who is allowed."** It only defines how to handle an already-rendered denial.
- **"Returning null is always better than 403."** Fallbacks can break contracts, mask errors, or cause false successes.
- **"`@PostAuthorize` denials automatically roll back the database."** The body already ran; side effects require explicit transaction/check design.
- **"Proxies work everywhere."** Self-invocation, `final` methods, unwrapped targets, and certain serializers can bypass interception.
- **"Adding `@RequiresPermission` always resolves placeholders."** Requires the template bean and a supporting version.
- **"Combining a `@PreAuthorize` meta-annotation with a direct annotation ANDs them as intended."** Repeated identical annotations are unsupported; design one explicit policy.
- **"The Spring Boot starter enables method security automatically."** `@EnableMethodSecurity` is required.
- **"Patching the app guarantees the Security version is safe."** Check resolved dependencies and specific advisories; 6.3.0/6.3.1 had missing-advice cases.
- **"Passing service tests means serialization is safe."** Test real endpoints with JSON/GraphQL formats and active serializers.
- **"Passing on JVM means passing on native image."** AOT generic/proxy runtime hints require separate verification.
- **"Role ADMIN overrides every object ACL."** If admin exceptions exist, specify them explicitly in domain policy and audit them; never grant automatic bypasses via annotations.

## 15. Exercises and Acceptance Criteria

**Exercise A — Identify supported versions.** Given three apps using Spring Security 6.2, 6.3.2, and 6.4+, list which annotations work natively, which need replacement with explicit service policies, and why 6.3.0/6.3.1 must not be used in advisory-affected scenarios.

**Exercise B — Field protection.** Add `phoneNumber` to `ProfileView` and create authority `profile:phone`. Verify an actor permitted to read the profile but lacking field permission never receives the phone number, even after JSON serialization. Weigh returning `null` vs. a masked string: when does a contract permit each?

**Exercise C — Annotation templates.** Create `@RequiresPermission("profile:edit")` for a method with no pre-authorization side effects. Test with and without the authority. Omit the template bean in an isolated test to compare outcomes, then fix so enforcement works. Do not stack two `@PreAuthorize`s on one method.

**Exercise D — Migration and proxies.** Test direct objects, `Optional<ProfileView>`, and `List<ProfileView>`. Confirm which methods are actually wrapped by proxies. Try a record/`final` type and document limitations; never ship to production without serializer-path tests.

**Completion checklist:** verified resolved Spring Security dependencies and patches; enabled method security; service policy enforces object/tenant boundaries; returned objects are proxied on the right paths; each sensitive getter has annotations/policies; deny handlers return type-safe outputs; template beans are enabled on supporting versions; both allow/deny and negative controls tested; zero data leaks or side effects on denial; and active collection/AOT/serializer shapes verified.

## Official References

- Spring Security 6.5 — Method Security, Return Objects, Denied Results, Meta-Annotation Templates: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security — `@AuthorizeReturnObject` Javadoc (Since 6.3): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/method/AuthorizeReturnObject.html
- Spring Security — `@HandleAuthorizationDenied` Javadoc (Since 6.3): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/method/HandleAuthorizationDenied.html
- Spring Security — `MethodAuthorizationDeniedHandler` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/method/MethodAuthorizationDeniedHandler.html
- Spring Security — `AnnotationTemplateExpressionDefaults` Javadoc (Since 6.4): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/annotation/AnnotationTemplateExpressionDefaults.html
- Spring Security Advisory — CVE-2024-38810 (6.3.0/6.3.1, fix 6.3.2): https://spring.io/security/cve-2024-38810/
