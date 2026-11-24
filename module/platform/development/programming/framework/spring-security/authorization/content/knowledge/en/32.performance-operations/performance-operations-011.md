# AOT, Native Image, and Version-Based Compatibility Checks for Proxies and Expressions

## 1. Goals and Scope

Spring Security enforces authorization at the HTTP request level via `SecurityFilterChain`/`AuthorizationManager` and at the method level via `@EnableMethodSecurity`, `@PreAuthorize`, `@PostAuthorize`, and Spring AOP advisors. When moving an application from standard JVM to **Spring AOT** (Ahead-of-Time) or **GraalVM Native Image**, security rules must keep working accurately even though the framework prepares beans, proxies, reflection, and metadata differently.

The critical questions are: are unauthorized users truly blocked **before** sensitive services execute? Can a SpEL expression still resolve methods, fields, custom principals, and policy beans in native mode? Do bean calls actually pass through the security proxy? Does your Spring Security/Framework version support the annotations and runtime hints in use? These questions must be answered by tests, not merely by seeing the executable start up.

After this lesson, learners should be able to:

1. Distinguish **standard JVM, JVM with generated AOT code, and native image**; know what is fixed at build time.
2. Explain proxy-based method security, JDK interface proxies, class-based proxies, and where advice is bypassed.
3. Diagnose SpEL failures caused by missing parameter metadata, dynamic property access, custom principals, policy beans, or reflection hints.
4. Build a compatibility matrix across Spring Boot, Spring Framework, Spring Security, GraalVM, Native Build Tools, and build configuration.
5. Test **ALLOW, DENY, expression errors, and side effects** across JVM/AOT/native; release only with zero authorization regressions.

This lesson belongs to **Performance and Operations**, so it also evaluates startup, memory, build time, latency, and operations. Never relax authorization rules just to make native compilation succeed or improve startup time.

## 2. How Does AOT Differ from Native Image?

| Mode | Mechanism | What Tests Verify |
| --- | --- | --- |
| Standard JVM | Spring builds context, creates proxies, and uses reflection flexibly at runtime | Baseline authorization behavior |
| JVM AOT | Spring uses pre-generated bean definitions/initializers/proxy assets on the JVM | Effects of build-time bean graph and proxies |
| GraalVM Native Image | GraalVM runs closed-world analysis and compiles a platform executable | Reachability of classes, methods, resources, reflection, dynamic proxies; live security behavior |

**AOT does not mean native.** Spring AOT can generate Java sources and proxy bytecode either to run on the JVM or to feed GraalVM image builds. Native adds constraints around static analysis, reflection, resource loading, serialization, and proxy forms. Passing JVM tests does not guarantee native passes. Passing `nativeCompile` does not guarantee `@PreAuthorize` works on every service either.

Spring AOT typically generates:

- Bean-initialization Java code replacing parts of runtime configuration analysis.
- Pre-generated proxy bytecode before application startup.
- Runtime hints for reflection, JDK proxies, resources, serialization, and JNI when needed.

With Gradle, assets may appear under `build/generated/aotSources`, `build/generated/aotClasses`, and `build/generated/aotResources`. Paths vary by plugin version; inspect your actual artifacts.

### 2.1. Boundaries of Build-Time Configuration

Spring AOT evaluates many bean-creation conditions at build time. Therefore you cannot assume flipping `@Profile`, `@ConditionalOnProperty`, or a `SecurityFilterChain` condition at runtime will materialize an entirely new bean graph. Use **the exact profile and bean conditions** intended for the native release. Runtime values like policy service URLs or credentials are managed separately from bean existence; never bake secrets into build artifacts just to force configuration activation.

If a production policy bean exists only under the `prod` profile yet the native image was built under another profile, failures may surface as missing beans or a different authorization fallback. That is a build/runtime configuration bug, never a reason to permit by default. Inspect `SecurityFilterChain`s and method-security advisors discovered by AOT before packaging the image.

## 3. Method Security and Proxy Mechanics

When `@EnableMethodSecurity` is enabled, Spring Security registers method interceptors. `@PreAuthorize` runs **before** the target method call; `@PostAuthorize` runs **after** the method returns. This mechanism relies on calls passing through a **Spring-managed proxy**, rather than injecting authorization checks into every plain Java call automatically.

~~~text
Calling Controller / Bean
       |
       v
Spring-managed DocumentService proxy
       |
       +--> @PreAuthorize advisor
       |       DENY => stop, target is not invoked
       |
       +--> DocumentService.method(...)
       |
       +--> @PostAuthorize advisor (if configured)
       |
       v
     Result
~~~

| Characteristic | JDK Interface Proxy | Class-Based Proxy (typically CGLIB) |
| --- | --- | --- |
| Proxy creation | Object implementing one or more interfaces | Subclass of the target class |
| Call site | Callers must work through the proxied interface | Methods/classes must be overridable |
| Risks | Casting/injecting directly as concrete class fails; methods absent from interface | `final` classes or `final` methods cannot be overridden; `private` methods are not advised by subclassing |
| With AOT/native | Custom dynamic JDK proxies may need proxy hints if AOT cannot infer them | Needs pre-generated/registered proxy classes |
| Testing | Check proxy and call through actual bean/interface | Check proxy, method visibility, and calls through Spring bean |

Spring can pre-generate many standard framework proxies ahead of time. Never add reflection/proxy hints for an entire package as a blanket fix: pinpoint the exact missing type and member.

### 3.1. Self-Invocation

~~~text
another bean -> proxy.export() -> advice -> target.export()
another bean -> proxy.batch() -> target.batch() -> this.export()
                                                     |
                                                     +-- never re-enters proxy
~~~

Suppose `@PreAuthorize` is placed only on `export()`, while `batch()` calls `this.export()`. In the standard proxy model, `this.export()` can **bypass `export()`'s advisor**. This vulnerability exists in both JVM and native; registering `RuntimeHints` will not fix it.

Prefer protecting the `batch()` entry point too, or extracting `export()` into another Spring bean invoked through a Spring-managed proxy. Avoid manually pulling proxies from the context or self-injecting if cleaner service boundaries are possible. Tests should deliberately exercise both direct calls from other beans and internal calls.

### 3.2. `@PostAuthorize` Does Not Undo Side Effects

`@PreAuthorize` denies before the method runs; `@PostAuthorize` can only reject **the return value** after the method has already sent notifications, deleted documents, or committed transactions. Never rely solely on post-authorization to guard irreversible writes. `@PreFilter`/`@PostFilter` also need behavioral tests on real collections/inputs/outputs; they do not replace permission checks where side effects happen.


## 4. SpEL Expressions and Runtime Hints Differences

Examples in Spring Security:

~~~java
@PreAuthorize("hasAuthority('DOC_READ')")
public Document getDocument(String documentId) { /* ... */ }

@PreAuthorize("@documentPolicy.mayUpdate(authentication, #documentId)")
public void updateDocument(String documentId) { /* ... */ }

@PostAuthorize("returnObject.owner == authentication.name")
public Document getOwnedDocument(String documentId) { /* ... */ }
~~~

These are **method snippets inside Spring-managed beans**, requiring `@EnableMethodSecurity`, a `documentPolicy` bean, and a `Document` type; they are not standalone Java. Checking ownership via `@PostAuthorize` makes sense only for read paths, not for protecting writes with side effects.

| Expression Component | What Must Be Verified |
| --- | --- |
| `hasAuthority('DOC_READ')` | Exact `GrantedAuthority` name present in `Authentication` |
| `hasRole('ADMIN')` | `ROLE_` prefix rules per config; do not confuse with `hasAuthority` |
| `authentication`, `principal` | Actual runtime `Authentication`/`principal` reaching Spring Security |
| `#documentId` | Method parameter names retained or discovered accurately |
| `@documentPolicy.mayUpdate(...)` | Policy bean present in context and method resolved by SpEL |
| `principal.isAdmin()` or `principal.canExport(id)` | Custom principal methods may need reflection hints in native |
| `returnObject.owner` | Property getter/field/type accessible dynamically via SpEL |
| `hasPermission(...)`, `PermissionEvaluator` | Are custom evaluation handlers and beans AOT-compatible? |
| `@PreFilter`/`@PostFilter` | `filterObject`/`returnObject`, generic types, per-item outcomes |
| Annotations/APIs from newer versions | Truly present in pinned dependencies, or only in latest docs? |

### 4.1. Parameter Names Must Be Explicit

SpEL using `#documentId` can fail when method parameter names are absent in bytecode or differ between interface and implementation. Use the Java compiler `-parameters` flag or Spring Security's `@P` annotation for explicit naming; never assume JVM and native infer parameter names identically from debug metadata.

~~~java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;

@PreAuthorize("@documentPolicy.mayUpdate(authentication, #docId)")
public void update(@P("docId") String documentId) {
    // Place inside a real Spring bean
}
~~~

This snippet requires a `documentPolicy` bean and Spring Security dependencies. `#docId` evaluating to null or throwing evaluation errors must never silently pass as allowed. Write tests for parameter names, null inputs, cross-tenant IDs, unauthorized principals, and policy bean failures.

### 4.2. Reflection on Custom Principals

On the JVM, SpEL often calls methods on custom `UserDetails`/`Authentication` principals via reflection. In native mode, methods outside the reachability graph can lack reflection metadata, producing `SpelEvaluationException` (e.g., `EL1004E`: method `isAdmin()` cannot be found on principal type). There are **multiple** causes for `EL1004E`: typo in name, different runtime principal type, non-public method, missing bean, or missing hint. Prove the exact cause before adding hints.

If an expression references a bean by name when that bean was excluded by `@ConditionalOnProperty`/profile during the AOT build, reflection hints will not recreate the missing bean; fix the bean condition config and rebuild.


### 4.3. `RuntimeHintsRegistrar` for Exact Methods

Suppose the project has class `AppPrincipal` with `public boolean canExport(String documentId)`, and `@PreAuthorize` invokes `principal.canExport(#documentId)`. Once native tests prove SpEL cannot invoke that method, register **the exact method**:

~~~java
import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

final class PrincipalExpressionHints implements RuntimeHintsRegistrar {
    @Override
    public void registerHints(RuntimeHints hints, ClassLoader loader) {
        try {
            hints.reflection().registerMethod(
                    AppPrincipal.class.getMethod("canExport", String.class),
                    ExecutableMode.INVOKE
            );
        } catch (NoSuchMethodException exception) {
            throw new IllegalStateException(
                    "SpEL accessor is missing", exception);
        }
    }
}

@Configuration
@ImportRuntimeHints(PrincipalExpressionHints.class)
class NativeAuthorizationHintsConfiguration {
}
~~~

This is a **Spring Framework integration pattern**, requiring `AppPrincipal` and a compatible `RuntimeHints` API version; it does not compile standalone with `javac`. If expressions access other getters/fields, register those exact members. For data binding/serialization, `@RegisterReflectionForBinding` can help in certain versions, yet never assume it covers every custom SpEL method hint automatically.

Never register entire packages or broad class sets "just to be safe." Runtime hints preserve metadata in native images; **they do not change permissions**. After adding hints, re-run both denied and allowed tests on the native executable. Tests checking only that hints exist do not prove the policy executes properly.

If custom libraries construct JDK dynamic proxies themselves or read config files outside the classpath, proxy/resource hints may be needed. Spring AOT generally generates Spring AOP proxies; add manual hints only with evidence. The GraalVM tracing agent helps discover missing reflection/resource/proxy entries, yet collected metadata must be reviewed and stripped of test-only artifacts.

### 4.4. Classifying Root Causes

- **Policy bug:** bad expression, mismatched role/authority, wrong tenant data -> fix the rule.
- **Proxy bug:** `this.method()`, bean instantiated with `new`, `final`/`private` method, wrong target injection -> fix AOP boundaries.
- **Bean graph bug:** conditional bean omitted by AOT -> fix build profiles/conditions.
- **Reachability bug:** missing method/resource/dynamic-proxy metadata -> register exact hint.
- **Library version bug:** missing API, changed annotation, incompatible plugin -> align via BOM/migration guide.

Keep fail-closed behavior intact: policy evaluation errors must never become ALLOW. A native 500 is an operational bug to fix; a native 200 for an unauthorized principal is a critical security regression.

## 5. Version Matrix and Branch-Matched Documentation

| Component | What to Pin / Check | Risk |
| --- | --- | --- |
| JDK, GraalVM | Version, Native Image toolchain, OS/architecture | Native executable and reflection compatibility |
| Spring Boot | Major/minor/patch and Gradle/Maven plugin | AOT tasks, auto-config, buildpacks, hints |
| Spring Framework | Version managed by Boot BOM | AOP, bean initialization, `RuntimeHints` API |
| Spring Security | Version managed by Boot BOM | `AuthorizationManager`, SpEL, advisors, available features |
| Native Build Tools | Plugin version compatible with GraalVM/Boot | `nativeCompile`/`nativeTest` |
| Policy/JSON/HTTP libraries | Exact versions, reachability metadata | Serialization, TLS, dynamic proxies |
| Build profiles/conditions | Bean-creation conditions, feature flags | Accurate build-time bean graph and filter chains |
| Deployment | JVM/AOT/native share same data and security contract | Avoid misinterpreting config mismatches |

With **Spring Boot 3.3.x**, Spring Framework typically aligns with **6.1.x** and Spring Security with **6.3.x** under Boot's dependency management. Inspect your application's resolved versions rather than hardcoding patch assumptions. When upgrading to Boot 3.4/3.5/4.x or Spring Security 6.5/7.x, read the migration guide and re-run the full suite.

Features such as return-object proxying, `@AuthorizeReturnObject`, and newer registrars/hints introduced in newer Spring Security releases may **not exist or have different APIs** in 6.3. Never copy 6.5/7.x snippets into 6.3 simply because docs default to `latest`. A `cannot find symbol` error is an API/version mismatch, never fixed by a reflection hint.

Also check: is `@EnableMethodSecurity` enabled? Spring Boot Starter Security does not turn on method-level authorization automatically. Which annotation styles are enabled (`prePostEnabled`, `securedEnabled`, `jsr250Enabled`)? Are there multiple `SecurityFilterChain`s with differing orders? Do URL rules and method rules share the intended protection?

Separate **compile errors** (wrong API), **AOT generation errors** (bean/proxy graph), **native-image build errors** (reachability/toolchain), **native startup errors** (resources/initialization), and **runtime authorization errors** (SpEL/permissions/proxies). Never apply one generic hint to fix every failure category.



## 6. Standalone Java 17+ Example: Seeing Self-Invocation Clearly

The program below uses only the JDK to simulate a JDK interface proxy. It intentionally illustrates the bug where **a guard protects only `export` while another method invokes `export` via `this`, bypassing the advisor**. This is a counterexample for testing, not how to configure Spring Method Security or build a native image.

Save as **`AuthorizationProxyDemo.java`**:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public class AuthorizationProxyDemo {
    interface DocumentOperations {
        String export();
        String batchExport();
    }

    static final class DocumentService implements DocumentOperations {
        @Override
        public String export() {
            return "PRIVATE-DATA";
        }

        @Override
        public String batchExport() {
            return this.export();
        }
    }

    static DocumentOperations guarded(DocumentOperations target, boolean allowed) {
        return (DocumentOperations) Proxy.newProxyInstance(
                DocumentOperations.class.getClassLoader(),
                new Class<?>[] { DocumentOperations.class },
                (proxy, method, args) -> {
                    if (method.getName().equals("export") && !allowed) {
                        throw new SecurityException("export denied");
                    }
                    try {
                        return method.invoke(target, args);
                    } catch (InvocationTargetException ex) {
                        throw ex.getCause();
                    }
                }
        );
    }

    public static void main(String[] args) {
        DocumentOperations service = guarded(new DocumentService(), false);

        try {
            service.export();
            throw new AssertionError("expected denial");
        } catch (SecurityException expected) {
            System.out.println("proxy.export -> DENIED");
        }

        String bypass = service.batchExport();
        if (!"PRIVATE-DATA".equals(bypass)) {
            throw new AssertionError("unexpected example result");
        }
        System.out.println("proxy.batchExport -> PRIVATE-DATA (self-invocation)");

        DocumentOperations privileged = guarded(new DocumentService(), true);
        System.out.println("privileged.export -> " + privileged.export());
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac --release 17 AuthorizationProxyDemo.java
java AuthorizationProxyDemo
~~~

Exact stdout:

~~~text
proxy.export -> DENIED
proxy.batchExport -> PRIVATE-DATA (self-invocation)
privileged.export -> PRIVATE-DATA
~~~

**Explanation:** calling `service.export()` enters the proxy handler and is blocked when `allowed=false`. Calling `service.batchExport()` is intercepted only at the `batchExport` entry point; inside the target, `this.export()` goes straight to the implementation, returning the private data anyway. The lesson is to guard entry points and test proxy boundaries. In real Spring applications, guard `batchExport` with an appropriate policy or extract export logic into another bean invoked through a security proxy. Never rely on reflection hints to patch this behavior.

### 6.1. Distinguishing Standalone Java from Framework Examples

In the demo, `Proxy.newProxyInstance` is called directly. Spring applications typically let Spring AOP manage proxies; for native, Spring AOT pre-generates needed proxies. Only when your own application creates dynamic JDK proxies over runtime-determined types should you evaluate `registerJdkProxy` in `RuntimeHints`. Never register every interface blindly without a failing test proving the need.

## 7. Spring Security 6.x Integration Example

The snippets below are **excerpts from a Spring Boot/Spring Security application**, requiring matching dependencies and controllers/beans; they cannot run standalone with `javac` like section 6.

HTTP and method security configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
class AuthorizationConfiguration {
    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/documents/**")
                    .hasAuthority("DOC_READ")
                .requestMatchers(HttpMethod.POST, "/api/documents/**")
                    .hasAuthority("DOC_WRITE")
                .anyRequest().denyAll());
        return http.build();
    }
}
~~~

Method security on the service:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class DocumentApplicationService {

    @PreAuthorize("hasAuthority('DOC_READ')")
    public String read(String id) {
        return "document:" + id;
    }

    @PreAuthorize("hasAuthority('DOC_WRITE')")
    public void change(String id, String content) {
        // Write data only after proxy has allowed it
    }
}
~~~

This configuration illustrates permissions only; a real application also needs authentication, CSRF/CORS, endpoint mappings, and object-level authorization for tenant/owner. HTTP matchers alone are insufficient to protect per-document permissions. Unannotated methods get no automatic method-security checks; the trailing `denyAll` at the HTTP layer protects only requests through that chain, not service calls from batch/job/event consumers.

Proper test: inject the **Spring-managed `DocumentApplicationService`** into a controller or another bean, authenticate an identity holding only `DOC_READ`, and call `change()`. Assert DENY **and** assert DB/write state did not change. Calling `new DocumentApplicationService()` directly has no proxy and does not test `@PreAuthorize`. For JDK interface proxies, inject the interface rather than casting to the implementation class.

### 7.1. Replacing Complex SpEL with a Java `AuthorizationManager`

Decisions spanning many tenant attributes, resources, policy services, or remote timeouts are often easier to test when typed cleanly inside an `AuthorizationManager`/policy bean. For HTTP requests, use `access(customAuthorizationManager)`; at the method level, configure a method-security advisor/authorization manager matching your version. Benefits include clear separation of `ALLOW`/`DENY`/`INVALID`/`UNAVAILABLE`, clean telemetry, and less reliance on reflective property access. Still, **typed Java code does not automatically cure self-invocation or missing proxies**; you must still test the entire call path.


## 8. Building and Testing with Gradle

The commands below illustrate a Spring Boot Gradle application **that already applies the GraalVM Native Build Tools plugin compatible with your Spring Boot and GraalVM versions**. Task names may differ or not exist in subprojects without native configured. Use the repository's Gradle Wrapper and target only supported projects.

~~~bash
# JVM baseline
./gradlew test

# Run Spring AOT processing to generate Java/proxy/hints assets
./gradlew processAot

# Build GraalVM native executable (requires native-image toolchain)
./gradlew nativeCompile

# Native tests, requires native test support
./gradlew nativeTest

# Optional container image via configured Docker/Buildpacks
./gradlew bootBuildImage
~~~

On Windows, typically use `gradlew.bat`; multi-project builds need the Gradle project path and task (e.g. `:service:nativeCompile`). Do not assume the root project applies every plugin automatically. `nativeCompile` can consume substantial CPU/RAM and build time. `bootBuildImage` requires a Docker daemon and a native-compatible builder; installing `native-image` directly on the host is not mandatory in all buildpack setups.

**Dedicated JVM AOT verification:** if a build packages AOT code, Spring Boot docs describe running the JAR on the JVM with `-Dspring.aot.enabled=true`. Turning on that property against a JAR lacking generated AOT assets is not a valid AOT test. Before trusting results, inspect the artifact to verify AOT-generated initializers/proxy bytecode/hints are present.

### 8.1. Three QA Tiers Before Release

1. **Unit tests** for policy beans/`AuthorizationManager`: inputs, authorities, tenant, deny, invalid, timeout; requires no native toolchain.
2. **Spring integration tests** with `ApplicationContext`/`SecurityFilterChain`: call via real managed beans/HTTP, verify `@PreAuthorize` and zero side effects. Also verify custom principal/bean expressions resolve cleanly.
3. **Native tests**: run the actual executable and send production-like requests; compare data, statuses, audits/metrics, and DB state against the JVM baseline. Use `nativeTest` or external HTTP tests targeting the built image depending on your project.

A test verifying only that the application starts or testing only the allowed path is insufficient. Prove denied paths; never turn exceptions into `permitAll`. For write operations, inspect DB records before/after or verify the target service was never invoked.

### 8.2. Cross-Environment Behavior Matrix

| Scenario | Standard JVM | JVM AOT | Native | Evidence to Assert |
| --- | --- | --- | --- | --- |
| Principal with `DOC_READ` calls `read` | ALLOW | ALLOW | ALLOW | Right data/endpoint |
| Principal without `DOC_READ` | DENY | DENY | DENY | No sensitive data returned |
| Principal with only `DOC_READ` calls `change` | DENY | DENY | DENY | Target not run, DB unchanged |
| Valid `DOC_WRITE` calls `change` | ALLOW | ALLOW | ALLOW | Authorized on object/tenant |
| Wrong tenant or object ID | DENY | DENY | DENY | No IDOR/BOLA |
| Called from another bean via proxy | Advisor runs | Advisor runs | Advisor runs | Interceptor applies to right method |
| Self-invocation or `final` method | Test catches and architecture fixed | Same contract | Same contract | Zero bypasses |
| SpEL `#paramName` | Resolves cleanly | Resolves cleanly | Resolves cleanly | No unexpected nulls |
| `@documentPolicy` bean method | Calls right bean | Calls right bean | Calls right bean | No resolution errors |
| Custom principal method | Right result | Right result | Right result | Reflection hints present if needed |
| `@PostAuthorize` with owner check | DENY on wrong object | DENY | DENY | No return-value leakage |
| Anonymous / invalid token | Never enters service | Never enters service | Never enters service | Appropriate entry point |
| Policy exception / timeout | Never ALLOW | Never ALLOW | Never ALLOW | Fail closed, telemetry emitted |
| Multiple `SecurityFilterChain`s | Matches right chain | Matches right chain | Matches right chain | No exposed alternate route |
| Build profile / feature flag | Right bean graph | Right bean graph | Right bean graph | Config honors same test contract |

Exact HTTP status codes can vary by `AuthenticationEntryPoint`, `AccessDeniedHandler`, or exception handling; the fundamental invariant is that when unauthorized, sensitive endpoints **must produce zero side effects**. A SpEL error can yield 500 instead of 403; that still requires fixing and must never count as a pass merely because access was not granted.

### 8.3. Testing Proxies in Spring `ApplicationContext`

For services using standard method security, verify Spring-managed beans have appropriate proxies, then **test real DENY behavior**. JUnit/Spring Boot snippet, not a standalone Java file:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class MethodSecurityProxyIT {
    @Autowired DocumentApplicationService documents;

    @Test
    void beanUsesSpringAopProxy() {
        assertThat(AopUtils.isAopProxy(documents)).isTrue();
    }
}
~~~

`isAopProxy=true` alone does not prove the advisor enforces the right policy. Add a test using a principal lacking `DOC_WRITE` calling `documents.change()` on this bean, assert `AccessDeniedException` or HTTP 403 per context, and verify data did not change. If a valid setup uses an authorization mechanism not built on Spring AOP proxies, do not apply this test mechanically; test the actual enforcement boundary.

### 8.4. Testing Hints

You can construct `RuntimeHints`, invoke your registrar, and use `RuntimeHintsPredicates` to verify reflection method/resource/proxy metadata per your version's API. That tests only **hint registration**; native integration tests are still needed to prove SpEL and real policies succeed at runtime. Test principals with and without permissions, cross-tenant objects, and throwing policy beans.

For `@PostAuthorize`/`@PostFilter`, test properties on real `returnObject`/`filterObject` instances, including parameterized collections; newer Spring Security versions add return-object proxying and hint registrars, so use them only if your pinned dependencies support them. Never assume identically named annotations work identically across major/minor branches.



## 9. Diagnosing Native Image Incidents

Investigate systematically from symptom to failing layer, keeping the same principal/request/resource when comparing:

1. **Record versions and inputs:** Spring Boot/Security/Framework versions, JDK/GraalVM, build profile, authorities, object ID/tenant, URL, and root exception. Avoid logging tokens/secrets.
2. **Run the JVM baseline:** if JVM also fails, focus on rules/matchers/proxies/SpEL logic; if only native fails, proceed to AOT/reachability steps.
3. **Verify beans and advice:** is `@EnableMethodSecurity` active? Does the bean have a Spring proxy? Do `final`/`private` methods or `this.method()` bypass interceptors?
4. **Inspect expressions:** are `#parameter` names, `@P`/`-parameters`, actual principal type, policy bean name, and property getters accurate?
5. **Inspect AOT outputs:** do generated bean registrations/proxy classes and resource metadata include what is needed? Did the build profile exclude beans?
6. **Pinpoint missing hints:** which exact method/property/resource/JDK proxy truly needs reflection/dynamic access? Register the exact target and rebuild.
7. **Re-run native tests:** test both ALLOW and DENY, cross-tenant objects, and policy errors; confirm zero unauthorized side effects.
8. **Compare on upgrades:** check dependency locks/BOMs, migration guides, native tooling, and new config changes.

| Symptom | Where to Check | What NOT to Do |
| --- | --- | --- |
| `EL1004E`: method not found in expression | Actual principal, method name, reflection metadata | Open `permitAll` to skip the error |
| 403 on JVM but 500 on native | SpEL root cause, custom method/bean hints | Treat 500 as success because data did not leak |
| 200 when missing permission | Proxy bypassed, broad rule, inactive annotation, fail-open logic | Blame GraalVM without checking advisors |
| Bean cast fails after proxying | JDK interface proxy vs concrete class injection | Force-cast to implementation |
| `nativeCompile` fails on proxy | Who creates the dynamic proxy, existing hints, plugin version | Add hints for entire packages |
| Policy template resource missing | Was the resource packaged/hinted properly? | Assume JVM local filesystem paths still exist |
| Built native with profile A, ran B | Fixed build-time bean graph | Expect `@ConditionalOnProperty` to create new beans at runtime |
| Self-invocation not blocked | Entry points and `this.method()` calls | Expect AOT to magically rewrite Spring AOP logic |

### 9.1. Distinguishing Reliability and Performance

Record minimum metrics: authorization granted/denied counts, SpEL/reflection error counts, policy evaluation latency, timeouts, policy adapter failures, and protected endpoint latency. When caching permissions, keys must include principal, action, resource, tenant, and policy-version/TTL per contract; never reuse stale ALLOWs indefinitely when the PDP fails.

Native images can reduce startup time and memory in some workloads, though compile times are longer and throughput/JIT/artifact size involve trade-offs. Measure on identical workloads, CPU/RAM, Spring Security policies, and HTTP clients. **Never disable Spring Security advisors or drop permission checks to win benchmarks.** If a remote policy service dominates latency, fast native startup will not erase network request costs.

## 10. Release Checklist

A trustworthy AOT/native release needs evidence for all of the following:

- Boot/Framework/Security/Native Build Tools/GraalVM/JDK versions locked; build steps/profiles reproducible.
- `SecurityFilterChain`s and policy beans present in the generated AOT graph; no reliance on implicitly created runtime beans.
- Method security genuinely active; sensitive methods invoked via proxies; zero unresolved self-invocation/`final`/`private` bypasses.
- Custom principals, expressions, policy beans, DTOs, resources, and dynamic proxies verified with exact hints where needed.
- Standard JVM, JVM AOT, and native produce identical ALLOW/DENY decisions for equivalent principal/action/resource inputs.
- Denied tests confirm zero data mutations and zero return-value leaks; allowed tests confirm business flows still work.
- Policy timeouts, malformed responses, missing reflection methods, and exceptions never turn into ALLOW.
- Proper error-typed logs/metrics exist without logging tokens/credentials, plus an artifact rollback plan.
- Startup, RAM, build time, throughput, and latency are measured empirically; optimizations are accepted only while authorization stays accurate.

**Final criterion:** AOT/native changes how an application is packaged, initialized, and stores metadata. It **must never** change who is allowed to read, modify, or delete a resource. Every version or build-mode change must preserve this invariant.

## 11. Official References

Use these links to verify against your exact framework branch before applying configs or APIs:

- [Spring Boot 3.3 — Advanced Native Images Topics](https://docs.spring.io/spring-boot/3.3/reference/packaging/native-image/advanced-topics.html): tracing agent, `RuntimeHints`, resource/proxy configuration, native limitations.
- [Spring Boot — Introducing GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html): closed world, AOT Java sources, hints, and proxy bytecode.
- [Spring Framework — Ahead-of-Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html): AOT engine, `RuntimeHints` API.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, `@PostAuthorize`, proxies, SpEL.
- [Spring Security — Method Security in GraalVM Native Image](https://docs.spring.io/spring-security/reference/native-image/method-security.html): custom `UserDetails`/`Authentication` reflection and hints; current page may differ from 6.3, so select your exact version before using APIs.
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `AuthorizationManager` and HTTP rules.

