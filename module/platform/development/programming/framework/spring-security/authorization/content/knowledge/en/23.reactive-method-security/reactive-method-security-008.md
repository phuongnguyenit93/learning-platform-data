# Proxies, Self-Invocation, and Conditions for Interceptors to Apply

> **Module:** Spring Security – Authorization. **Topic:** Reactive Method Security. This lesson explains how `@PreAuthorize`/`@PostAuthorize` are applied via Spring AOP proxies, why `this.method()` bypasses advice, requirements for Spring-managed beans and reactive return types, JDK proxy vs. CGLIB differences, `private`/`final` limitations, and how to test using Java 17+, Spring Boot 3.x, Spring Security 6.x, Reactor `StepVerifier`, and `WebTestClient`.

## 1. The Problem: An Annotation Does Not Mean Every Call Is Intercepted

~~~java
@Service
public class DocumentService {

    @PreAuthorize("hasAuthority('DOC_APPROVE')")
    public Mono<String> approve() {
        return Mono.just("approved");
    }

    public Mono<String> approveInternally() {
        return this.approve();
    }
}
~~~

A call from another bean to `documentService.approve()` goes through the Spring bean proxy and triggers the method-security interceptor. However, `this.approve()` inside the target itself is **self-invocation**; under default Spring AOP proxying, internal calls do not re-enter the proxy, so the annotation on `approve()` is **not evaluated for that call**.

~~~text
External bean -> Spring proxy -> method-security advice -> target.approve()

External bean -> proxy -> target.approveInternally()
                               |
                               +-> this.approve() (bypasses proxy)
~~~

This is an issue of **interceptor application boundaries**, not a `Mono` bug, not Spring Security silently turning off, and not something solved by switching from JDK proxies to CGLIB.

**Rule:** protected business entry points must have security policies actually execute, verified by tests following production call paths. Never rely merely on seeing an annotation in source code.

## 2. Structure of Reactive Method Security

| Component | Role |
| --- | --- |
| `Authentication` | Verified principal and authorities |
| `ReactiveSecurityContextHolder` | Reads `SecurityContext` from Reactor Context |
| `@EnableReactiveMethodSecurity` | Enables advisors/interceptors for reactive methods |
| `@PreAuthorize` | Declares permission condition before method execution |
| `@PostAuthorize` | Checks condition after method under reactive semantics |
| `AuthorizationManager` | Modern Spring Security ALLOW/DENY decision API |
| Spring AOP proxy | Intercepts invocations passing through the bean proxy |
| Target object | Executes business method |
| `Mono`/`Flux` | Publisher reflecting result/error when subscribed |

Spring Security 6.x can be configured as:

~~~java
@Configuration
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
class MethodSecurityConfiguration {
}
~~~

Spring AOP builds a proxy for eligible beans. When calls go through the proxy, the advisor recognizes `@PreAuthorize`, retrieves `Authentication` via **Reactor Context** during reactive evaluation, and grants or denies according to the expression.

### Distinguishing Invocation from Subscription

~~~text
1. Caller invokes securedBean.operation() via proxy.
2. Spring reactive interceptor creates/wraps the appropriate Publisher.
3. WebFlux/StepVerifier subscribes to the Publisher.
4. Authentication in subscriber's Reactor Context is used for authorization.
5. If denied: Publisher emits AccessDeniedException.
6. If allowed: business Publisher can execute.
~~~

Tests that only invoke `Mono<?> p = bean.operation()` or `assertNotNull(p)` do not prove enforcement. Tests must **subscribe** using `StepVerifier` or `WebTestClient.exchange()`. Side effects should live inside reactive sources (`Mono.defer` or reactive repositories) rather than running eagerly before permissions are checked.

Reactive Method Security differs from Servlet Method Security configuration: `@EnableWebFluxSecurity` enables only WebFlux HTTP security and does not replace `@EnableReactiveMethodSecurity` when protecting service methods.

## 3. Targets, Proxies, and Self-Invocation

Suppose we have:

~~~java
@Service
class ApplicationService {
    public Mono<String> outer() {
        return inner();
    }

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> inner() {
        return Mono.just("operation-result");
    }
}
~~~

If the application calls `service.outer()` externally:
- The `outer` invocation enters the proxy and delegates to the target.
- Inside the target, `inner()` is equivalent to `this.inner()`.
- The call to `inner` never goes back through the proxy.
- Advice on `inner` does not execute along that call path.

Even when `outer` is `public`, `inner` is `public`, the bean is `@Service`, and security annotations are enabled, **the proxy requirement is still unsatisfied**.

### Call Paths to Distinguish

| Call Path | Through Proxy? | Relevant Behavior |
| --- | --- | --- |
| Controller injects bean and calls annotated method | Yes, if injection returns proxy | Interceptor can run |
| Bean A injects bean B and calls annotated method on B | Yes | Interceptor can run |
| Method in same target calls `this.secured()` | No | Method advice is skipped |
| Method in same target calls `secured()` without `this` | No | Still self-invocation |
| Manual `new Service()` outside Spring context | No | No Spring AOP |
| `@Bean` returns container-managed instance | Possible | Container can wrap in proxy |
| Annotated `private` helper | No | Not a proxy boundary |
| CGLIB class with `final` method | Cannot advise that method | Cannot be overridden |
| JDK proxy injected by interface | Yes | Interface methods can be intercepted |
| Method not yet subscribed to | Insufficient evidence | Cannot conclude decision ran |

If the outer proxied method already enforces sufficient security rules for the action, an internal call to a helper does not automatically create a vulnerability. Risk arises when **the actual security boundary sits only on the internally invoked method**, or when another unguarded entry point exists.

## 4. JDK Dynamic Proxies vs. CGLIB

Spring AOP typically picks one of two mechanisms:

| Characteristic | JDK Proxy | CGLIB / Class-Based Proxy |
| --- | --- | --- |
| What is proxied? | Interface(s) | Subclass of target |
| Stable injection type | Interface | Class or interface |
| Concrete method absent from interface | Not exposed on interface proxy | Can be advised if eligible |
| `final class` | Can proxy via interface depending on config | Cannot be subclassed |
| `final method` | Depends on invocation via interface proxy | Cannot be overridden/advised by subclass |
| `private method` | Not a public interface method | Cannot be overridden/advised |
| Self-invocation | Not advised | Not advised |

Never assume the exact proxy type solely because a class implements an interface: Spring Boot and AOP configuration can alter the strategy. Check with:

~~~java
AopUtils.isAopProxy(bean);
AopUtils.isJdkDynamicProxy(bean);
AopUtils.isCglibProxy(bean);
~~~

These are **inspection helpers** inside a context/test importing `org.springframework.aop.support.AopUtils`, not a standalone program.

### Visibility Cases

- **`private`:** cannot be overridden by class-based proxies; never place the sole security check on a `private` method.
- **`final` method:** class-based proxies cannot override it; do not rely on it as an interception point under CGLIB.
- **`final` class:** cannot be subclassed for CGLIB proxying; interface-based proxying is a separate case to test.
- **`protected`/package-private:** advisability depends on proxy type, version, and visibility. Prefer **`public` service methods** for authorization boundaries.
- **`static` methods/constructors:** not standard instance-method boundaries for Spring AOP proxies.
- **Kotlin:** classes and methods are `final` by default; usually requires `kotlin-spring`/all-open plugin for Spring-managed classes.
- **Java modules/JPMS:** restricted package/visibility exports can affect CGLIB.
- **JDK proxies:** injecting the concrete implementation type may fail; inject the interface when using interface proxies.

Setting `proxyTargetClass=true` does not fix self-invocation. It only changes how proxies are generated.

## 5. Pure Java 17: Seeing Self-Calls Bypass a Proxy

The illustration below uses JDK `Proxy`, **not Spring Security's implementation**. It clarifies why an internal call never passes back through the proxy.

**`ProxyLab.java`**

~~~java
import java.lang.reflect.Proxy;

public class ProxyLab {
    public interface Operations {
        String guarded();
        String fromWithin();
    }

    static class Target implements Operations {
        @Override
        public String guarded() {
            return "TARGET METHOD";
        }

        @Override
        public String fromWithin() {
            return this.guarded();
        }
    }

    public static void main(String[] args) {
        Target target = new Target();
        Operations proxy = (Operations) Proxy.newProxyInstance(
                ProxyLab.class.getClassLoader(),
                new Class<?>[]{Operations.class},
                (p, method, arguments) -> {
                    if (method.getName().equals("guarded")) {
                        return "PROXY INTERCEPTED";
                    }
                    return method.invoke(target, arguments);
                });

        System.out.println(proxy.guarded());
        System.out.println(proxy.fromWithin());
    }
}
~~~

Compile and run:

~~~bash
javac ProxyLab.java
java ProxyLab
~~~

**Exact stdout:**

~~~text
PROXY INTERCEPTED
TARGET METHOD
~~~

The first call goes through `InvocationHandler` and is intercepted. The second invokes `Target.fromWithin()`; inside the target, `this.guarded()` runs directly. This sample includes no sensitive data and exists solely to demonstrate how proxies work.

## 6. Runnable WebFlux / Spring Security Example

Java 17+ project with Gradle, Spring Boot 3.x (e.g., 3.5.x), and Spring Security 6.x. We create:
- A security configuration enabling WebFlux and Reactive Method Security.
- A `GuardedService` with an annotated method plus a self-call method **strictly for testing**.
- A `SafeFacade` in another bean injecting `GuardedService`.
- A controller exposing **only the proxied paths**, never the self-call method.
- Integration tests verifying both HTTP role enforcement and advice via Reactor `StepVerifier`.

### 6.1. `settings.gradle`

~~~groovy
rootProject.name = 'reactive-proxy-lab'
~~~

### 6.2. `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo.proxy'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 6.3. `src/main/java/demo/proxy/ReactiveProxyApplication.java`

~~~java
package demo.proxy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveProxyApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveProxyApplication.class, args);
    }
}
~~~

### 6.4. `src/main/java/demo/proxy/ReactiveSecurityConfiguration.java`

~~~java
package demo.proxy;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class ReactiveSecurityConfiguration {
    @Bean
    SecurityWebFilterChain web(ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers("/api/public").permitAll()
                        .pathMatchers("/api/direct", "/api/facade")
                        .authenticated()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        PasswordEncoder encoder =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails viewer = User.withUsername("viewer")
                .password(encoder.encode("viewer-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build();

        return new MapReactiveUserDetailsService(viewer, admin);
    }
}
~~~

`@EnableReactiveMethodSecurity` applies annotations on the service, whereas `SecurityWebFilterChain` only requires authentication on the two routes. That lets tests distinguish the **HTTP auth gate** from the **method role gate**. `hasRole("ADMIN")` checks the `ROLE_ADMIN` authority (created by `roles("ADMIN")`). The in-memory user store and sample passwords must never be used in production.

### 6.5. `src/main/java/demo/proxy/GuardedService.java`

~~~java
package demo.proxy;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class GuardedService {
    private final AtomicInteger executions = new AtomicInteger();

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> perform() {
        return Mono.defer(() -> {
            executions.incrementAndGet();
            return Mono.just("operation-performed");
        });
    }

    // Used only in self-invocation behavior tests.
    // Do not expose this method in an HTTP API.
    public Mono<String> unsafeInternalCall() {
        return this.perform();
    }

    public int executionCount() {
        return executions.get();
    }
}
~~~

Placing work inside `Mono.defer` ensures business logic does not run when the publisher is denied. `unsafeInternalCall` is a **counterexample**, not a recommended API. Calling `perform` from within the target itself does not go through the proxy.

### 6.6. `src/main/java/demo/proxy/SafeFacade.java`

~~~java
package demo.proxy;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class SafeFacade {
    private final GuardedService guarded;

    public SafeFacade(GuardedService guarded) {
        this.guarded = guarded;
    }

    public Mono<String> performFromAnotherBean() {
        return guarded.perform();
    }
}
~~~

This is the preferred fix: the facade and service are **two separate Spring beans**. `SafeFacade` calls `GuardedService` via an injected dependency, meaning the call traverses the bean proxy.

### 6.7. `src/main/java/demo/proxy/ExampleController.java`

~~~java
package demo.proxy;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ExampleController {
    private final GuardedService guarded;
    private final SafeFacade facade;

    public ExampleController(
            GuardedService guarded,
            SafeFacade facade) {
        this.guarded = guarded;
        this.facade = facade;
    }

    @GetMapping("/api/public")
    public Mono<String> publicPing() {
        return Mono.just("pong");
    }

    @GetMapping("/api/direct")
    public Mono<String> direct() {
        return guarded.perform();
    }

    @GetMapping("/api/facade")
    public Mono<String> facade() {
        return facade.performFromAnotherBean();
    }
}
~~~

There is no route for `unsafeInternalCall()`. Both production-intended paths in the demo reach `GuardedService.perform()` through the Spring bean proxy. In systems with sensitive data, also check per-resource owner/tenant/permissions; a generic `ROLE_ADMIN` alone is insufficient.

## 7. Testing Proxies and Real Call Paths

**`src/test/java/demo/proxy/ProxyIntegrationTest.java`**

~~~java
package demo.proxy;

import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(
        classes = ReactiveProxyApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class ProxyIntegrationTest {
    @Autowired ApplicationContext context;
    @Autowired GuardedService guarded;
    @Autowired SafeFacade facade;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    private Authentication auth(String name, String authority) {
        return new UsernamePasswordAuthenticationToken(
                name, "test-only",
                List.of(new SimpleGrantedAuthority(authority)));
    }

    @Test
    void guardedBeanIsAProxy() {
        assertTrue(AopUtils.isAopProxy(guarded));
    }

    @Test
    void anonymousCannotCallDirect() {
        client.get().uri("/api/direct")
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedViewerCannotCallDirect() {
        client.get().uri("/api/direct")
                .headers(h -> h.setBasicAuth(
                        "viewer", "viewer-pass"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void authenticatedViewerCannotCallFacade() {
        client.get().uri("/api/facade")
                .headers(h -> h.setBasicAuth(
                        "viewer", "viewer-pass"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void adminCanCallBothRoutes() {
        client.get().uri("/api/direct")
                .headers(h -> h.setBasicAuth(
                        "admin", "admin-pass"))
                .exchange().expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("operation-performed");

        client.get().uri("/api/facade")
                .headers(h -> h.setBasicAuth(
                        "admin", "admin-pass"))
                .exchange().expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("operation-performed");
    }

    @Test
    void deniedSubscriptionDoesNotExecuteBusinessWork() {
        int before = guarded.executionCount();

        StepVerifier.create(guarded.perform()
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(
                                auth("viewer", "ROLE_USER"))))
                .expectError(AccessDeniedException.class)
                .verify();

        assertEquals(before, guarded.executionCount());
    }

    @Test
    void adminSubscriptionPerformsWork() {
        StepVerifier.create(guarded.perform()
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(
                                auth("admin", "ROLE_ADMIN"))))
                .expectNext("operation-performed")
                .verifyComplete();
    }

    @Test
    void internalCallDemonstratesMissingInterception() {
        // Intentionally demonstrates self-invocation bypassing the proxy.
        StepVerifier.create(guarded.unsafeInternalCall()
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(
                                auth("viewer", "ROLE_USER"))))
                .expectNext("operation-performed")
                .verifyComplete();
    }

    @Test
    void separateBeanCallUsesTheInterceptor() {
        StepVerifier.create(facade.performFromAnotherBean()
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(
                                auth("viewer", "ROLE_USER"))))
                .expectError(AccessDeniedException.class)
                .verify();
    }

    @Test
    void plainNewObjectIsNotProxied() {
        GuardedService manuallyCreated = new GuardedService();
        assertFalse(AopUtils.isAopProxy(manuallyCreated));

        StepVerifier.create(manuallyCreated.perform())
                .expectNext("operation-performed")
                .verifyComplete();
    }

    @Test
    void publicRouteIsPublic() {
        client.get().uri("/api/public")
                .exchange().expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }
}
~~~

### 7.1. Why Did the Internal Test "Pass"?

`internalCallDemonstratesMissingInterception` **deliberately** illustrates that the method annotation is not applied on self-invocation. That is **something to eliminate from production code**, not a desired permission policy. The main controller does not expose that path. After finishing this exercise, delete or refactor `unsafeInternalCall`.

### 7.2. Test Matrix

| Test | Expected Result |
| --- | --- |
| `GuardedService` bean from Spring Context | `AopUtils.isAopProxy` = `true` |
| Anonymous `GET /api/direct` | HTTP 401 |
| Viewer `GET /api/direct` | HTTP 403 |
| Viewer `GET /api/facade` | HTTP 403 |
| Admin `GET /api/direct`, `/api/facade` | HTTP 200, `operation-performed` |
| Viewer calls `guarded.perform()` via proxy with `StepVerifier` | `AccessDeniedException` |
| Denied publisher | `executionCount` does not increment |
| Admin calls `perform()` | Publisher completes with value |
| Viewer calls `unsafeInternalCall()` | Returns value, proving missing interception |
| Viewer calls via proper facade | `AccessDeniedException` |
| Manual `new GuardedService()` | Not an AOP proxy |
| Anonymous `GET /api/public` | HTTP 200 |

### 7.3. Running the Tests

~~~bash
./gradlew test --tests demo.proxy.ProxyIntegrationTest
./gradlew bootRun
~~~

Windows:

~~~text
gradlew.bat test --tests demo.proxy.ProxyIntegrationTest
gradlew.bat bootRun
~~~

Testing HTTP:

~~~bash
curl -i http://localhost:8080/api/direct
curl -i -u viewer:viewer-pass http://localhost:8080/api/direct
curl -i -u admin:admin-pass http://localhost:8080/api/facade
~~~

Expected responses are 401, 403, and 200 with body `operation-performed`, respectively. This lesson was verified statically; run the tests on your actual project and versions before production use. Never leave demo passwords in real environment logs or shell history.

## 8. Conditions Required for the Interceptor to Actually Apply

1. **Dependencies and configuration:** Spring Security and `@EnableReactiveMethodSecurity` are present. Do not confuse with `@EnableWebFluxSecurity`, which only guards HTTP.
2. **Managed bean:** the service must be Spring-managed; directly instantiated objects have no proxy.
3. **Annotation resolution:** `@PreAuthorize` is placed on the proper method/class, without conflicts or placement unsupported by that Spring version.
4. **Proxyable method:** the method is exposed cleanly for JDK/CGLIB proxying; avoid incompatible `private`/`final` methods.
5. **External call:** the invocation enters via the proxy, not `this.method()` or a constructor.
6. **Reactive signature:** return type is a supported `Publisher` (typically `Mono`/`Flux`); do not switch to a blocking return type and expect reactive method security to behave identically.
7. **Reactor Context:** when the `Publisher` is subscribed to, a trusted `Authentication` with the right authorities is present.
8. **Subscription:** the `Publisher` is actually subscribed to; `StepVerifier`/`WebTestClient` prove allow/deny.
9. **No swallowed errors:** `AccessDeniedException` is never turned into sensitive data via `onErrorResume`.
10. **Business protection:** tenant/owner/resource checks are still evaluated independently of coarse-grained roles.

### Why Can't `@PostAuthorize` Save Self-Invocation?

`@PostAuthorize` is also method-security advice wired via AOP. If a call bypasses the proxy, post-check annotations do not run on that call either. Moreover, post-checks must never be the sole safeguard for irreversible side effects (sending emails/events, deleting remote files). Authorize before mutations and use transactions/outboxes when needed.

## 9. Fixing Self-Invocation Properly

### 9.1. Extract the Public Method to Another Bean (Preferred)

~~~text
Controller
   |
   v
Facade bean
   |
   v
Protected bean PROXY
   |
   +-> @PreAuthorize + reactive service implementation
~~~

Advantages: clear boundaries, easy to test, minimal coupling to Spring internals, and no circular dependencies. `SafeFacade` in the project uses this approach.

### 9.2. Place the Annotation on the Actual Public Entry Point

If public method `outer` is the sole permitted entry path, annotate it directly:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public Mono<String> outer() {
    return innerHelper();
}
~~~

**This is an illustrative snippet**: `innerHelper` must be defined, with no other public path bypassing `outer`. The precondition is that **all sensitive paths enter through the guarded entry point**. If another endpoint or worker calls the helper directly, add a dedicated boundary there.

### 9.3. Self-Injection

You can inject a self-proxy where appropriate, but it easily leads to circular dependencies and type mismatches with JDK proxies. Prefer extracting a separate bean. Always test that the injected instance is actually a proxy.

### 9.4. `AopContext.currentProxy()`

Spring AOP offers `AopContext.currentProxy()` when `exposeProxy` is enabled, but this couples business code to AOP internals. In reactive flows that switch schedulers/threads, relying on a ThreadLocal-backed current proxy at the wrong moment is fragile. Avoid using it as a default pattern.

### 9.5. AspectJ Weaving

AspectJ compile-time or load-time weaving applies advice in bytecode, avoiding Spring AOP proxy self-invocation limits. However, it is a different build/runtime mechanism requiring dedicated setup and testing rather than a single annotation toggle. For typical WebFlux applications, splitting beans cleanly is simpler and safer.

## 10. Observable Failures and How to Diagnose Them

| Symptom | Cause | Fix |
| --- | --- | --- |
| `@PreAuthorize` does not block despite annotation | Reactive method security not enabled | Add `@EnableReactiveMethodSecurity` |
| Viewer denied via direct call, allowed via internal call | Self-invocation | Extract bean or guard the entry point |
| Test creating object via `new` is not blocked | No proxy | Inject Spring bean in integration tests |
| `AopUtils.isAopProxy` = `false` | Bean not proxied / annotation not applied | Check dependencies, config, method |
| Concrete class injection fails | JDK interface proxy | Inject interface or adjust proxy strategy |
| `final` class fails to proxy | CGLIB requires subclassing | Remove `final` or use an interface |
| `private` method annotated with no effect | Private methods not intercepted | Guard `public` methods |
| No `Authentication` in `StepVerifier` | Missing Reactor Context | Add `contextWrite(withAuthentication(testAuth))` |
| Test only asserts the `Mono` object | Publisher never subscribed to | `StepVerifier.create(...).verify()` |
| HTTP 401 | Unauthenticated or bad credentials | Check authentication filter/entry point |
| HTTP 403 | Authenticated but missing authority | Check `hasRole`/`hasAuthority`/CSRF for unsafe methods |
| `block()` fails on Netty thread | Blocking in non-blocking context | Compose `Mono`/`Flux` |
| `@Transactional` also skipped in same class | Self-invocation bypasses proxy | Extract transactional bean, test transactions |
| Behavior changes after Boot upgrade | Proxy mode / annotation resolution changed | Run integration regression tests |
| User with right role reads wrong tenant | Missing resource-level checks | Bind tenant/owner/resource in policy |
| Error caught and returns success | `onErrorResume` fails open | Propagate access denied; return no payload |
| `Mono.cache()` shares user data | Cache not partitioned by identity | Never globally cache auth-dependent values |

## 11. `@Transactional`, Caching, and WebFlux Context

`@Transactional`, `@Cacheable`, and Method Security can all rely on proxies. Calling an internal method via `this` can skip transaction advice **as well as** authorization. Reactive `@Transactional` requires a compatible `ReactiveTransactionManager` and execution inside a reactive transaction context; having a security context does not automatically provide a transaction.

Never assume advisor ordering between transactions and security purely from annotation order in source. When policy needs to read the DB inside the same transaction or prevent races with permission changes, verify with integration tests, transaction isolation, locks, or revision-aware policies.

**Reactor Context** carries authentication per subscription; imperative `ThreadLocal`-based `SecurityContextHolder` is not a reliable default source in WebFlux. Never call `.subscribe()` or `.block()` inside reactive services. Never write `Authentication` into Context from untrusted inputs.

A service can be properly proxied and still enforce weak object-level authorization if `@PreAuthorize("hasRole('ADMIN')")` ignores tenant, owner, and resource state. Method Security is a policy enforcement point; it **does not automatically know** every business constraint.

## 12. Pre-Production Checklist

1. Are `@EnableReactiveMethodSecurity` and compatible dependencies enabled?
2. Are protected methods `public` service entry points returning `Mono`/`Flux`?
3. Is the bean from `ApplicationContext` actually a Spring AOP proxy?
4. Are there any `this.securedMethod()` calls, self-invocations, or direct constructor calls?
5. Does the JDK/CGLIB proxy mode align with interfaces, `final` modifiers, and visibility?
6. Do tests cover both direct invocation and real facade/controller call paths?
7. Do negative tests for unauthorized users subscribe and receive `AccessDeniedException`?
8. Do tests prove a denied publisher never mutates business state?
9. Do HTTP tests distinguish 401 (unauthenticated) from 403 (insufficient authority)?
10. Are there any URLs or worker paths reaching unguarded methods?
11. Does Reactive Context hold verified principals rather than forged header values?
12. Is `AccessDeniedException` never swallowed into a data-returning fallback?
13. Are complex self-injections/circular dependencies avoided in favor of bean extraction?
14. Is `@PostAuthorize` never used as the sole guard after side effects?
15. Do document/tenant operations enforce resource-level permission checks?
16. Are `@Transactional`/`@Cacheable` and Method Security tested together when combined?
17. Is Kotlin `all-open` or JPMS proxy visibility configured if applicable?
18. Does CI run tests using Spring context, Reactor `StepVerifier`, and `WebTestClient`?

## 13. Exercises

**Exercise 1:** Compile and run `ProxyLab.java` with `javac`/`java`. Explain both stdout lines and how they relate to Spring AOP.

**Exercise 2:** Use `StepVerifier` to call `GuardedService.perform` through the Spring bean as `viewer`, then call `unsafeInternalCall`. Explain why the outcomes differ even though both invoke `perform`.

**Exercise 3:** Refactor the code so no unguarded internal call path exists. Move the guard to a separate bean or place the annotation on the real entry point.

**Exercise 4:** Add `@PreAuthorize("hasAuthority('DOC_APPROVE')")` to a method returning `Mono`. Test `USER` without permission and `ADMIN` with permission when business scope allows it.

**Exercise 5:** Use `AopUtils` to inspect JDK vs. CGLIB proxies in projects with and without interfaces. Test a `final` method and record each proxy type's limits.

**Exercise 6:** Put a side effect inside `Mono.defer` and measure counters before and after a deny. Verify zero business side effects when permission is denied.

**Exercise 7:** Implement a document- and tenant-scoped rule. Verify an account with `ROLE_ADMIN` in tenant A cannot modify tenant B documents.

**Exercise 8:** Use `WebTestClient` to test HTTP Basic, 401, 403, and 200. Then temporarily remove `@EnableReactiveMethodSecurity` in a test branch and verify your security tests catch the regression.

**Exercise 9:** Combine `@Transactional` and `@PreAuthorize` on reactive services with a reactive database to demonstrate how self-invocation can break both transaction and authorization boundaries.

**Completion criteria:** distinguish target vs. proxy, explain JDK vs. CGLIB and `private`/`final`, identify self-invocation causes, describe reactive `Publisher`/Reactor Context prerequisites, and have integration tests proving interceptors actually execute.

## Official References

- Spring Security – Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security 6.5 – Reactive Method Security: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
- Spring Framework 6.2 – Proxying Mechanisms, self-invocation: https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html
- Spring Security – ReactiveSecurityContextHolder API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- Spring Security – WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security – WebFlux test setup: https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html
- Spring Framework – Declarative transactions: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Reactor – Context: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
