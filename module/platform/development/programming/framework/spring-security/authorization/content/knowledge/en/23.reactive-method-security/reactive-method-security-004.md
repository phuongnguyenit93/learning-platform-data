# ReactiveAuthorizationManager with MethodInvocation

> **Module:** Spring Security – Authorization · **Topic:** Reactive Method Security. This Knowledge lesson dives into `ReactiveAuthorizationManager<MethodInvocation>`: how Spring Security protects a method returning `Mono`/`Flux` with an asynchronous decision, uses `MethodInvocation` to inspect the method/arguments, uses `Mono<Authentication>` from the Reactor Context, and wires a custom authorization manager into `AuthorizationManagerBeforeReactiveMethodInterceptor`. The Spring APIs and snippets target **Spring Security 6.5.x, Spring Boot 3.x, Spring WebFlux, Java 17+**. Spring Security 7.x changes the `authorize` interface; do not mix signatures from both versions when copying code. A standalone JDK 17 example at the end illustrates invocation-based decisions without external dependencies.

## 1. What Should You Be Able to Do After This Lesson?

1. Distinguish authorization at reactive methods, reactive HTTP requests, and servlet methods; do not confuse the generic type `MethodInvocation` with `ServerWebExchange` or `MethodInvocationResult`.
2. Explain Reactor Context and the role of `ReactiveSecurityContextHolder`, instead of reading thread-local `SecurityContextHolder` inside a WebFlux pipeline.
3. Understand the `ReactiveAuthorizationManager<MethodInvocation>` signature in Spring Security 6.5: `check(Mono<Authentication>, MethodInvocation)` returning `Mono<AuthorizationDecision>`; `authorize` is the newer transitional API.
4. Use `MethodInvocation#getMethod()`, `getArguments()`, and `getThis()` to build authorization requests; validate types, lengths, and tenants from method arguments.
5. Implement a non-blocking custom manager that returns an explicit DENY when `Authentication`, membership data, arguments, or the policy service fail or are missing.
6. Register a custom advisor for a dedicated annotation using `AnnotationMatchingPointcut.forMethodAnnotation`, avoiding accidentally overriding default `@PreAuthorize`.
7. Build a Spring Boot WebFlux application with `@EnableReactiveMethodSecurity(useAuthorizationManager=true)` and services returning `Mono`, enforcing user/tenant checks and resource-scoped repositories.
8. Test GRANT/DENY permissions via `WebTestClient` and `StepVerifier`, including cases where the same resource ID exists in two tenants.
9. Analyze `Mono.empty()` (abstain), `block()` inside reactive chains, eager side effects, self-invocation, mis-scoped authorization caching, context loss, and time-of-check/time-of-use.
10. Distinguish custom method interceptors from `@PreAuthorize` expressions calling a bean returning `Mono<Boolean>`, choosing appropriately for policy scale.
11. Classify pre- vs. post-invocation: checking permissions before execution with `MethodInvocation`, and checking return values with `MethodInvocationResult`/post-authorization or domain object policies.

## 2. Context: How Does Reactive Method Authorization Differ from Servlet?

In traditional Spring MVC/Servlet apps, method security typically uses:

~~~java
AuthorizationManager<MethodInvocation> manager;  // Imperative
// authorize(Supplier<Authentication>, MethodInvocation) ...
~~~

In WebFlux/Reactor, each subscription's authentication is stored in the **Reactor Context**, so reactive method security works with:

~~~java
ReactiveAuthorizationManager<MethodInvocation> manager; // Reactive
// Spring Security 6.5.x:
// check(Mono<Authentication>, MethodInvocation)
// -> Mono<AuthorizationDecision>
~~~

This is an **API illustration**, not a standalone Java program. Related types:

| API | Decision target | Where is it typically used? |
| --- | --- | --- |
| `AuthorizationManager<MethodInvocation>` | Invocation and `Supplier<Authentication>` | Imperative/Servlet method security |
| `ReactiveAuthorizationManager<MethodInvocation>` | Invocation and reactive `Authentication` | **Reactive before-method security** |
| `ReactiveAuthorizationManager<AuthorizationContext>` | Request authorization context | `ServerHttpSecurity.authorizeExchange(...).access(...)` |
| `ReactiveAuthorizationManager<MethodInvocationResult>` | Invocation and result object | Reactive **after-method** authorization |
| `ReactiveSecurityContextHolder` | Subscriber's Reactor `Context` | Supplies security context to reactive pipelines |
| `AuthorizationDecision` | `isGranted()` true/false | Explicit policy result |

**Never** create `ReactiveAuthorizationManager<ServerWebExchange>` and pass it to `AuthorizationManagerBeforeReactiveMethodInterceptor`: the generic type is incompatible and the semantic object differs. `MethodInvocation` represents an AOP-intercepted Java method call and does not contain an HTTP request by default.

### 2.1. Reactor Context Is Scoped to the Subscription

~~~text
WebFilter authenticates request
    |
    v
Reactor Context holds SecurityContext/Authentication
    |
    v
Spring AOP reactive method interceptor
    |
    +-- manager receives Mono<Authentication> for subscription
    |       |
    |       +-- asynchronous policy/tenant checks
    |       |
    |       +-- GRANT -> lets method Publisher continue
    |       +-- DENY  -> publisher errors with AccessDeniedException
    |
    v
Mono/Flux business result
~~~

Because authentication travels with the reactive subscription, calling `SecurityContextHolder.getContext()` directly in an arbitrary callback can return an empty context or the wrong thread's context; never treat it as the standard way to read identity in WebFlux. A custom manager is **already passed `Mono<Authentication>` by the framework**—use that publisher directly.

### 2.2. Cold Publishers and Lazy Side Effects

A `Mono<Doc>` service should defer I/O until subscription, e.g., with `Mono.defer(...)` or reactive repository APIs; do not run side-effecting reads or writes while the method is merely **constructing the Publisher**. Method security protects the **subscribe/emit path** and must not rely on an eager body that triggers remote side effects before policy runs.

Never call `.block()`, `.blockOptional()`, `.toFuture().get()`, `Thread.sleep`, or blocking JDBC/JPA directly on the event loop. For legacy blocking I/O that cannot yet be replaced, isolate it on a dedicated scheduler (`Schedulers.boundedElastic()`) and weigh security and latency; offloading alone does not solve transaction or context propagation.

## 3. Exact Spring Security 6.5 API Signatures and Upgrade Notes

In Spring Security **6.5.x**, `ReactiveAuthorizationManager<T>` defines `check(Mono<Authentication>, T)` returning `Mono<AuthorizationDecision>`. `check` is marked deprecated in recent 6.5 releases in favor of `authorize(Mono<Authentication>, T)` returning `Mono<AuthorizationResult>`; exact implementation depends on your version. Because `check` remains the method to implement on the 6.5 interface, the examples below implement `check` and explicitly note the version rather than mixing both forms.

~~~java
// Spring Security 6.5.x: contract excerpt.
public final class TenantReadAuthorizationManager
        implements ReactiveAuthorizationManager<MethodInvocation> {

    @Override
    @SuppressWarnings("deprecation")
    public Mono<AuthorizationDecision> check(
            Mono<Authentication> authentication,
            MethodInvocation invocation) {

        // Must return an actual publisher, never null.
        return Mono.just(new AuthorizationDecision(false));
    }
}
~~~

In Spring Security 7.x, check the JavaDoc for `ReactiveAuthorizationManager#authorize` in your build dependency and update the signature and return type accordingly. Never take the `Supplier<Authentication>` signature from **imperative** `AuthorizationManager` and put it on a reactive manager. Some reference snippets across docs may differ from a specific minor version's JavaDoc; **your actual dependency API is the source of truth for compilation**.

### 3.1. Mono.empty() Means No Decision, Not an Explicit DENY

In reactive authorization, a manager returning `Mono.empty()` signals **abstain / no conclusion**. How interceptors or composite managers treat abstain depends on configuration and version; for mandatory boundaries like tenant membership or resource ownership, never rely on an empty publisher to "auto-deny". Return:

~~~java
return Mono.just(new AuthorizationDecision(false));
~~~

when required authentication, tenant, or action is missing. In the full example, `defaultIfEmpty(DENY)` turns an empty authentication publisher or missing membership result into an explicit DENY.

### 3.2. Mono.error() Differs from DENY

`Mono.error(new IllegalStateException(...))` signals that the policy service failed; it does not mean the policy decided `false`. You can map that error to a fail-closed deny at the security boundary while recording separate `policy_unavailable` metrics. At the API layer, an outage may return 503 (denying data access), while a policy denial returns 403. Never catch all errors and default to granting access just to keep the service running.

### 3.3. What Can MethodInvocation Inspect?

~~~java
Method method = invocation.getMethod();
Object[] args = invocation.getArguments();
Object target = invocation.getThis();
String methodName = method.getName();
Class<?>[] types = method.getParameterTypes();
~~~

This snippet runs inside the method manager when `MethodInvocation invocation` is provided. Use those values to identify **which method** is called and **what arguments the caller passed**, not as proof that they are authorized. If a method receives `tenantId` from a URL, that value is a **selector** that must be checked against server-side membership. If a method takes `userId`, never treat it as the principal: derive the principal from the authenticated `Mono<Authentication>`.

The target may be a proxy or have bridge/generic methods. When inspecting annotations or parameter names via reflection, account for interface vs. implementation, bridge methods, and Spring's `AnnotatedElementUtils`/`AopUtils`. Avoid fragile index assumptions if service signatures change often; ideally constrain the annotation to a defined contract and test every signature shape.

## 4. When to Use a Custom Manager Instead of @PreAuthorize?

Both approaches are reactive method security:

**Simple:** use `@PreAuthorize("hasAuthority('document:read')")` when only an authority check is needed.

**Asynchronous data-driven policy:** use an expression bean:

~~~java
// Spring service excerpt:
// @PreAuthorize("@tenantPolicy.canRead(authentication, #tenant)")
// Mono<DocView> read(String tenant, Long id) { ... }
~~~

Spring Security reactive method expressions can support beans returning `Mono<Boolean>` when configured with AuthorizationManager mode. Ensure the expression invokes the bean via version-compatible SpEL and validates principal, tenant, and action. This is convenient for a few small rules, but when the same rule covers many methods and requires unified ordering, auditing, abstain handling, and context checks, a dedicated `ReactiveAuthorizationManager<MethodInvocation>` is easier to test.

**Custom AOP advisor:** define a `@TenantRead` annotation; the interceptor binds the manager to **every annotated method** without repeating expressions everywhere. It does not replace built-in `@PreAuthorize`. Other methods can still use `@PreAuthorize`; if both advices apply to one method, verify ordering so no early side effects occur.

## 5. Safe Design with MethodInvocation and Tenant

Suppose a service has the signature:

~~~java
@TenantRead
public Mono<DocView> read(String tenant, Long documentId) {
    return store.findWithinTenant(tenant, documentId)
            .map(doc -> new DocView(doc.id(), doc.tenant(), doc.title()));
}
~~~

Policy conditions:
- Reactive authentication holds a verified, non-anonymous user.
- The user has the `document:read` authority (feature gate).
- The tenant ID and `documentId` are valid.
- The user has READ membership in the **selected tenant** (not a different tenant).
- The query/loader reads only documents with the matching `tenant_id`; a valid `documentId` in another tenant must return no data.
- If object-level ACLs/ownership exist, enforce them separately using trusted resource metadata; tenant membership alone must not expose every document in the tenant.

An important insight: **the manager only sees method arguments and authentication**, whereas a record's true tenant is often known only after querying the repository. There are two design options:
1. The manager checks actor + membership + action **before invocation**; the service/repository performs only tenant-scoped queries, then applies object ACLs if required.
2. The manager performs a trusted reactive PIP lookup by tenant + ID before granting, and the service executes under appropriate transaction/version policies.

The demo chooses (1) to clearly illustrate `MethodInvocation`. Never take `tenantId` from an argument and treat it as `verifiedTenantId` without checking membership.

## 6. Complete Spring Boot WebFlux Demo: Custom @TenantRead Advisor

Guide files:

~~~text
src/main/java/demo/reactive/TenantMethodSecurityApplication.java
src/test/java/demo/reactive/TenantMethodSecurityApplicationTest.java
~~~

Create a Spring Boot **3.x** project, Java **17+**, using only the WebFlux and Security starters (do not add the Spring MVC starter for this sample). A single Java file with a `public` main class and package-private classes keeps the lesson concise. In production, separate domain, policy, repository, and web layers into files and packages with appropriate visibility and testability.

### 6.1. Application and Custom Manager

Save the following code as `src/main/java/demo/reactive/TenantMethodSecurityApplication.java`:

~~~java
package demo.reactive;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

import org.aopalliance.intercept.MethodInvocation;
import org.springframework.aop.Advisor;
import org.springframework.aop.support.annotation.AnnotationMatchingPointcut;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Role;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.authorization.method.AuthorizationManagerBeforeReactiveMethodInterceptor;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.security.config.web.server.ServerHttpSecurity;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class TenantMethodSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(TenantMethodSecurityApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain web(ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers("/api/tenants/**").authenticated()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
        // GET-only demo; do not disable CSRF arbitrarily.
    }

    @Bean
    MapReactiveUserDetailsService users() {
        return new MapReactiveUserDetailsService(
                User.withUsername("alice")
                    .password("{noop}demo")
                    .authorities("document:read")
                    .build(),
                User.withUsername("bob")
                    .password("{noop}demo")
                    .authorities("document:read")
                    .build(),
                User.withUsername("viewer")
                    .password("{noop}demo")
                    .authorities("profile:read")
                    .build());
        // {noop} is for demo ONLY, never use in production.
    }

    // Custom annotation so we do not replace built-in @PreAuthorize.
    @Bean
    @Role(BeanDefinition.ROLE_INFRASTRUCTURE)
    Advisor tenantReadAdvisor(TenantReadAuthorizationManager manager) {
        var pointcut = AnnotationMatchingPointcut
                .forMethodAnnotation(TenantRead.class);
        return new AuthorizationManagerBeforeReactiveMethodInterceptor(
                pointcut, manager);
    }
}

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@interface TenantRead {
}

record DocKey(String tenant, long id) {
}

record Doc(long id, String tenant, String title) {
}

record DocView(long id, String tenant, String title) {
}

// Demo PIP: server-side membership, never reads roles from HTTP headers.
@Component
class TenantMemberships {
    private final Map<String, Set<String>> readers = Map.of(
            "alice", Set.of("alpha"),
            "bob", Set.of("beta"),
            "viewer", Set.of("alpha"));

    Mono<Boolean> canRead(String user, String tenant) {
        return Mono.defer(() -> Mono.just(
                readers.getOrDefault(user, Set.of()).contains(tenant)));
    }
}

// This is Spring Security 6.5.x:
// ReactiveAuthorizationManager#check(Mono<Authentication>, MethodInvocation).
@Component
class TenantReadAuthorizationManager
        implements ReactiveAuthorizationManager<MethodInvocation> {

    private static final AuthorizationDecision DENY =
            new AuthorizationDecision(false);

    private final TenantMemberships memberships;

    TenantReadAuthorizationManager(TenantMemberships memberships) {
        this.memberships = memberships;
    }

    @Override
    @SuppressWarnings("deprecation")
    public Mono<AuthorizationDecision> check(
            Mono<Authentication> authentication,
            MethodInvocation invocation) {

        Object[] args = invocation.getArguments();
        if (args.length != 2
                || !(args[0] instanceof String tenant)
                || !(args[1] instanceof Long documentId)
                || documentId <= 0
                || !tenant.matches("[a-z][a-z0-9-]{0,31}")) {
            return Mono.just(DENY);
        }

        // Authentication is propagated by Spring Security via Reactor Context.
        // Do not read thread-local SecurityContextHolder.
        return authentication
                .filter(Authentication::isAuthenticated)
                .filter(a -> !(a instanceof AnonymousAuthenticationToken))
                .flatMap(a -> {
                    boolean featureAllowed =
                            a.getAuthorities().stream()
                                .map(GrantedAuthority::getAuthority)
                                .anyMatch("document:read"::equals);

                    if (!featureAllowed) {
                        return Mono.just(DENY);
                    }

                    // Server-side membership source, asynchronous.
                    return memberships.canRead(a.getName(), tenant)
                            .map(AuthorizationDecision::new)
                            .defaultIfEmpty(DENY);
                })
                .defaultIfEmpty(DENY)      // Missing Authentication => DENY.
                .onErrorReturn(DENY);      // PIP error => deny access.
    }
}

@Component
class DocumentStore {
    private final Map<DocKey, Doc> docs = Map.of(
            new DocKey("alpha", 7L),
                new Doc(7L, "alpha", "ALPHA:Budget"),
            new DocKey("beta", 7L),
                new Doc(7L, "beta", "BETA:Budget"),
            new DocKey("alpha", 8L),
                new Doc(8L, "alpha", "ALPHA:Notes"));

    Mono<Doc> findWithinTenant(String tenant, Long id) {
        // Cold publisher: does not read the store before subscription.
        return Mono.defer(() ->
                Mono.justOrEmpty(docs.get(new DocKey(tenant, id))));
    }
}

@Service
class DocumentService {
    private final DocumentStore store;

    DocumentService(DocumentStore store) {
        this.store = store;
    }

    @TenantRead
    public Mono<DocView> read(String tenant, Long id) {
        return store.findWithinTenant(tenant, id)
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(HttpStatus.NOT_FOUND)))
                .map(d -> new DocView(d.id(), d.tenant(), d.title()));
    }
}

@RestController
@RequestMapping("/api/tenants/{tenant}/documents")
class DocumentController {
    private final DocumentService service;

    DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    Mono<DocView> get(@PathVariable("tenant") String tenant,
                      @PathVariable("id") Long id) {
        return service.read(tenant, id);
    }
}
~~~

**Key code highlights:**
- `@EnableWebFluxSecurity` enables WebFlux HTTP security; `@EnableReactiveMethodSecurity(useAuthorizationManager=true)` enables reactive method security. Do not substitute imperative `@EnableMethodSecurity`.
- `@TenantRead` is a custom runtime marker annotation; `AnnotationMatchingPointcut.forMethodAnnotation(...)` matches methods bearing it.
- `AuthorizationManagerBeforeReactiveMethodInterceptor` wraps our `ReactiveAuthorizationManager<MethodInvocation>` and intercepts the service via Spring AOP.
- The manager reads `getArguments()`, validating types and length. It obtains `Authentication` from the **Mono supplied by the interceptor**, never from a caller-sent `userId`.
- `Mono.defer` in memberships/store ensures data is read only on subscription; in production, replace the in-memory map with a reactive database client.
- `defaultIfEmpty(DENY)` and `onErrorReturn(DENY)` enforce fail-closed behavior for mandatory checks; to distinguish outages in HTTP statuses/metrics, enhance policy error handling—never fall back to allow.
- `DocKey(tenant,id)` preserves scoping at the data source; the same `id=7` stays isolated across two tenants.
- `DocumentService.read` returns `Mono<DocView>`, avoiding blocking JPA.
- There is no object-specific ACL here: any tenant member with `document:read` can read all documents in that tenant. If your domain requires owner/ACL/classification checks, add them in the service/PIP; never treat this demo as proof that tenant membership replaces object authorization.
- The custom annotation can be placed on multiple service methods, provided **every method adheres to the argument contract**—otherwise the manager returns DENY. For diverse signatures, build a typed request resolver or annotation attributes and test them instead of making unchecked `args[0]` assumptions.
- In AOP proxy mode, calling `this.read(...)` within the same bean or constructing the service with `new` bypasses advice; always invoke through the Spring-managed proxy and test against real HTTP/service beans.

### 6.2. Gradle Dependencies

This is the `dependencies` block in a project already configured with the Spring Boot Gradle plugin, Java 17+, and dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Do not add `spring-boot-starter-web` (Servlet MVC) to this demo unless you intentionally choose the MVC stack. Reactor Test provides `StepVerifier`; Spring WebFlux/Test provides `WebTestClient`. With Maven/Gradle, manage compatible Spring Boot/Security versions (here 3.x/6.5.x). Check `./gradlew dependencies` if classpath mismatches occur; source snippets target Java 17.

### 6.3. Running and Testing via HTTP

Start from the configured Spring Boot project directory:

~~~bash
./gradlew bootRun
~~~

On Windows use `gradlew.bat bootRun`. Demo GET requests with HTTP Basic (learning environment only):

~~~bash
curl --user alice:demo http://localhost:8080/api/tenants/alpha/documents/7
curl --user bob:demo http://localhost:8080/api/tenants/beta/documents/7
curl --user bob:demo http://localhost:8080/api/tenants/alpha/documents/7
curl --user viewer:demo http://localhost:8080/api/tenants/alpha/documents/7
~~~

Expected outcomes:
- Alice reads alpha/7 ⇒ 200, title `ALPHA:Budget`.
- Bob reads beta/7 ⇒ 200, title `BETA:Budget`.
- Bob selects alpha ⇒ 403 (authenticated, missing membership).
- Viewer has alpha membership but lacks feature authority ⇒ 403.
- Anonymous lacks authentication ⇒ HTTP Basic entry point typically returns 401.
- Alice requests missing document ID 9 in alpha ⇒ 404.
- No routes outside `/api/tenants/**` are permitted.

`curl --user` in the demo sends Basic credentials over local HTTP; **production must use HTTPS**, never HTTP Basic with plain passwords as in this sample.

## 7. What Happens at Subscribe Time?

Trace Bob's request to `/api/tenants/beta/documents/7`:

~~~text
1. WebFlux Security authenticates Bob for request.
2. Controller invokes service proxy DocumentService.read("beta", 7L).
3. Reactive before-method interceptor recognizes @TenantRead.
4. Spring passes Mono<Authentication> bound to subscriber's context.
5. TenantReadAuthorizationManager validates:
   - exactly 2 args: String tenant, Long docId > 0
   - authenticated actor
   - document:read authority
   - Bob is a reader of beta
6. Manager emits AuthorizationDecision(true).
7. Service Publisher proceeds; store query uses DocKey("beta",7).
8. Response is BETA:Budget; alpha never used for lookup.
~~~

The manager must never call `.subscribe()` on its own to "pre-run the permission check": doing so detaches authorization from the request publisher and introduces unpredictable race and cancellation behavior. Return `Mono<AuthorizationDecision>` so the framework composes it directly. Reactive code should avoid side effects outside reactive operators; resolve identity from the active subscriber rather than a static ThreadLocal.

### 7.1. GRANT, DENY, ABSTAIN, and ERROR

| Scenario | What does the demo manager return? | Meaning |
| --- | --- | --- |
| Authenticated Alice, read authority, tenant alpha | `AuthorizationDecision(true)` | Allows the Publisher to proceed |
| Bob requests tenant alpha | `AuthorizationDecision(false)` | Deny |
| Anonymous or `Mono.empty()` auth | `AuthorizationDecision(false)` | Deny |
| Null/malformed tenant, null/negative id, mismatched signature | `AuthorizationDecision(false)` | Deny |
| Membership repository returns `Mono.empty()` | `AuthorizationDecision(false)` | Deny, not abstain |
| Membership repository error | `AuthorizationDecision(false)` | Fail closed; emit separate metrics |
| Custom manager returns `Mono.empty()` directly | **Abstain** | Undecided; never use for mandatory tenant gates |
| Custom manager returns `Mono.error(...)` | Error | Not ALLOW; map/propagate per contract |

If policy requires auditing every PIP failure, avoid silent `onErrorReturn(DENY)`: switch to `onErrorResume(error -> { metrics...; return Mono.just(DENY); })` without logging secrets or request bodies. Never call `onErrorReturn(new AuthorizationDecision(true))` in any branch.

### 7.2. Why Are @PreAuthorize and @TenantRead Not Identical?

`@PreAuthorize` is an expression annotation handled by Spring Security's built-in manager. `@TenantRead` is an application-defined marker handled by a dedicated `AuthorizationManagerBeforeReactiveMethodInterceptor`. Do not assume both share identical semantics across all behaviors: ordering, error handling, post-authorization, and auditing must be verified empirically.

If **both** `@PreAuthorize` and `@TenantRead` appear on one method, multiple advisors may execute. For mandatory checks, write tests confirming all run before any protected side effect executes; avoid accidental abstains or poorly understood ordering. Keeping a single custom marker or a single SpEL policy service reduces overlap.

## 8. WebFlux Integration Testing with WebTestClient

Using `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)`, the client sends HTTP Basic credentials through WebFlux security and Spring method AOP. Create `src/test/java/demo/reactive/TenantMethodSecurityApplicationTest.java`:

~~~java
package demo.reactive;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class TenantMethodSecurityApplicationTest {
    @Autowired WebTestClient client;

    @Test
    void aliceReadsAlpha() {
        client.get()
                .uri("/api/tenants/alpha/documents/7")
                .headers(h -> h.setBasicAuth("alice", "demo"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.tenant").isEqualTo("alpha")
                .jsonPath("$.title").isEqualTo("ALPHA:Budget");
    }

    @Test
    void bobReadsBetaWithSameIdButDifferentValue() {
        client.get()
                .uri("/api/tenants/beta/documents/7")
                .headers(h -> h.setBasicAuth("bob", "demo"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.tenant").isEqualTo("beta")
                .jsonPath("$.title").isEqualTo("BETA:Budget");
    }

    @Test
    void bobCannotSelectAlpha() {
        client.get()
                .uri("/api/tenants/alpha/documents/7")
                .headers(h -> h.setBasicAuth("bob", "demo"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void viewerCannotReadDespiteAlphaMembership() {
        client.get()
                .uri("/api/tenants/alpha/documents/7")
                .headers(h -> h.setBasicAuth("viewer", "demo"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void aliceCannotReadDocumentMissingInAlpha() {
        client.get()
                .uri("/api/tenants/alpha/documents/999")
                .headers(h -> h.setBasicAuth("alice", "demo"))
                .exchange()
                .expectStatus().isNotFound();
    }

    @Test
    void anonymousCannotAccessMethod() {
        client.get()
                .uri("/api/tenants/alpha/documents/7")
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
~~~

`WebTestClient` on `RANDOM_PORT` communicates over HTTP with a live reactive test server (unlike `MockMvc` for Servlet). In Boot/test setups with different auto-configuration, `@AutoConfigureWebTestClient` and appropriate binding may be used. Exact 403/404 status mapping may depend on custom error handling, but **cross-tenant content must never appear**.

### 8.1. Testing the Custom Manager Directly with StepVerifier

You can unit test without starting a server. Mock `MethodInvocation` with Mockito and assert with `StepVerifier`:

~~~java
// Test snippet with Spring Security/Mockito/Reactor Test.
// Required imports: MethodInvocation, TestingAuthenticationToken or
// UsernamePasswordAuthenticationToken, SimpleGrantedAuthority,
// StepVerifier, Mockito.mock/when, assertTrue/assertFalse.

MethodInvocation invocation = mock(MethodInvocation.class);
when(invocation.getArguments())
        .thenReturn(new Object[] {"alpha", 7L});

Authentication alice =
        UsernamePasswordAuthenticationToken.authenticated(
                "alice", "unused",
                java.util.List.of(
                        new SimpleGrantedAuthority("document:read")));

TenantReadAuthorizationManager manager =
        new TenantReadAuthorizationManager(new TenantMemberships());

StepVerifier.create(manager.check(Mono.just(alice), invocation))
        .assertNext(decision -> assertTrue(decision.isGranted()))
        .verifyComplete();

StepVerifier.create(manager.check(Mono.empty(), invocation))
        .assertNext(decision -> assertFalse(decision.isGranted()))
        .verifyComplete();
~~~

This is a snippet inside a test method, not a full Java file: add static imports for `org.mockito.Mockito.mock`/`when`, `org.junit.jupiter.api.Assertions.assertTrue`/`assertFalse`, and Spring Security/Reactor types. Also add cases for `args=[]`, wrong argument types, negative IDs, missing authorities, wrong tenants, membership errors, and incomplete sources. With Mockito mocks, `MethodInvocation#getArguments()` supplies the test object array directly; no HTTP request is made.

### 8.2. Testing Reactor Context Directly Through the Service Proxy

In a test with a Spring application context, inject `DocumentService` via `@Autowired` and attach authentication to the Reactor Context:

~~~java
// Snippet in JUnit with service as a Spring proxy:
Authentication alice =
        UsernamePasswordAuthenticationToken.authenticated(
            "alice", "unused",
            java.util.List.of(
                new SimpleGrantedAuthority("document:read")));

StepVerifier.create(
        documentService.read("alpha", 7L)
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(alice)))
    .expectNextMatches(view ->
            view.title().equals("ALPHA:Budget"))
    .verifyComplete();
~~~

If a test instantiates `new DocumentService(store)` or triggers self-invocation, the proxy advisor is skipped and the test proves nothing about method security. Always use `@Autowired DocumentService` so AOP applies. Another essential test runs as Bob calling `read("alpha", 7L)`: `StepVerifier.expectError(AccessDeniedException.class)` (or version-specific subtype) proves reactive DENY.

### 8.3. Mutation Tests to Safeguard the Test Suite

Intentionally remove:
- `@TenantRead` on `DocumentService.read` ⇒ Bob can read alpha because the HTTP gate only checks authentication; `bobCannotSelectAlpha` must fail.
- `memberships.canRead(...)` ⇒ Bob gets GRANT for alpha; tests must fail.
- Tenant predicate in `DocumentStore` ⇒ overlapping IDs across tenants can leak; tests with matching IDs across tenants must fail.
- `defaultIfEmpty(DENY)` in the manager ⇒ unauthenticated/empty auth can abstain; unit tests should fail.
- Feature authority rule ⇒ viewer with alpha membership can read; tests must fail.

These are negative quality checks for your test suite, never permitted changes in a real system.

## 9. Standalone Java 17: Simulating MethodInvocation and Decisions

Plain JDK has no Reactor, Spring Security, or AOP `MethodInvocation`. This program simulates **invocation-like data** using records and checks GRANT/DENY for mental modeling. It is **not a real `ReactiveAuthorizationManager` implementation** and cannot replace the Spring code in section 6.

Save `ReactiveMethodPolicyDemo.java`:

~~~java
import java.util.Map;
import java.util.Set;

public class ReactiveMethodPolicyDemo {
    record Actor(String name, Set<String> authorities,
                 Set<String> tenants) {}
    record Invocation(String methodName, String tenant, long docId) {}

    static final Map<String, Set<Long>> DOCUMENTS = Map.of(
            "alpha", Set.of(7L, 8L),
            "beta", Set.of(7L));

    static String check(Actor actor, Invocation call) {
        if (actor == null) {
            return "DENY_AUTH";
        }
        if (call == null || !"read".equals(call.methodName())
                || call.tenant() == null || call.docId() <= 0) {
            return "DENY_INVOCATION";
        }
        if (!actor.authorities().contains("document:read")) {
            return "DENY_FEATURE";
        }
        if (!actor.tenants().contains(call.tenant())) {
            return "DENY_TENANT";
        }
        if (!DOCUMENTS.getOrDefault(
                call.tenant(), Set.of()).contains(call.docId())) {
            return "NOT_FOUND";
        }
        return "GRANT";
    }

    public static void main(String[] args) {
        Actor alice = new Actor(
                "alice", Set.of("document:read"), Set.of("alpha"));
        Actor bob = new Actor(
                "bob", Set.of("document:read"), Set.of("beta"));
        Actor viewer = new Actor(
                "viewer", Set.of("profile:read"), Set.of("alpha"));

        System.out.println("alice-alpha7=" +
                check(alice, new Invocation("read", "alpha", 7L)));
        System.out.println("bob-beta7=" +
                check(bob, new Invocation("read", "beta", 7L)));
        System.out.println("bob-alpha7=" +
                check(bob, new Invocation("read", "alpha", 7L)));
        System.out.println("viewer-alpha7=" +
                check(viewer, new Invocation("read", "alpha", 7L)));
        System.out.println("alice-alpha999=" +
                check(alice, new Invocation("read", "alpha", 999L)));
        System.out.println("alice-write=" +
                check(alice, new Invocation("write", "alpha", 7L)));
        System.out.println("missing-auth=" +
                check(null, new Invocation("read", "alpha", 7L)));
        System.out.println("missing-tenant=" +
                check(alice, new Invocation("read", null, 7L)));
    }
}
~~~

Run with JDK 17:

~~~bash
javac --release 17 ReactiveMethodPolicyDemo.java
java ReactiveMethodPolicyDemo
~~~

**Exact stdout:**

~~~text
alice-alpha7=GRANT
bob-beta7=GRANT
bob-alpha7=DENY_TENANT
viewer-alpha7=DENY_FEATURE
alice-alpha999=NOT_FOUND
alice-write=DENY_INVOCATION
missing-auth=DENY_AUTH
missing-tenant=DENY_INVOCATION
~~~

This program illustrates that method name, arguments, and actor are separate items to validate, though in real reactive code `Authentication` arrives as a `Mono` from the framework and membership data may be fetched asynchronously.

## 10. When Are MethodInvocationResult and Post-Authorization Needed?

Before-method authorization uses `MethodInvocation` to inspect **method + arguments + authenticated actor** before returning results. For rules like "only the actual owner may view the record", you sometimes need resource metadata first or post-authorization on the returned object.

Spring Security provides `AuthorizationManagerAfterReactiveMethodInterceptor` and generic `ReactiveAuthorizationManager<MethodInvocationResult>` for post-checks on computed values; `@PostAuthorize` is a convenient option for many cases. However:
- Never perform protected side effects and check permissions afterward in `@PostAuthorize`. Use before-authorization and transaction guards for `DELETE`, payments, and external API calls.
- Output post-checks do not undo overly broad repository reads or sensitive logs written before denial.
- For a `Flux` returning thousands of elements, per-object filtering/checking needs a clear strategy for paging, total counts, and backpressure; never emit another tenant's element before denying.
- Post-authorization can emit an error when invalid; tests must also confirm no cross-tenant data is emitted.
- If a before-manager needs the resource owner, perform a trusted reactive PIP query by tenant + resource ID—never trust an owner supplied by the client.

## 11. Transaction, Tenant, and Async Scope

### 11.1. Tenant in Arguments Is Only a Selector

A call `read("beta", 7L)` passes tenant `beta`, yet Alice might not belong to `beta`. The manager must verify Alice's membership in `beta`, not just validate string syntax. If roles are tenant-specific, never let a global `ROLE_ADMIN` for `alpha` unlock `beta`. Resource rows must store their true tenant ID in the DB; every read/update/delete must stay within the trusted tenant scope.

### 11.2. Same ID, Different Tenant

When `alpha:7` and `beta:7` coexist, a cache key like `doc:7` or a global `findById(7)` repository query can mix records. Key caches, reads, writes, and invalidations by `(tenant, id)`; for ACL/user-specific responses, include actor/action/permission versions or re-authorize per request.

### 11.3. Role of R2DBC

In WebFlux, a reactive repository/R2DBC query must include the tenant predicate in SQL or database RLS where available. `Mono.defer` over an in-memory map in the demo only models non-blocking subscription—it does not make blocking JPA calls non-blocking. If accessing a blocking DB driver, isolate it on `boundedElastic` with a consistent contract or migrate to R2DBC; measure performance and ensure transaction context handling.

### 11.4. Race Between Check and Use

At t1 the manager verifies Bob is in `beta`; at t2 membership/ACL is revoked; at t3 the service writes data. For `WRITE`/`DELETE` or sensitive resources, execute queries under transactions, optimistic locking/versions/conditional writes, policy revisions, and invalidate access within your freshness SLA. Never assume an ALLOW at initial subscription holds forever across a long-lived stream.

### 11.5. Reactive Security Context and Schedulers

Reactor Context follows the subscription across `publishOn`/`subscribeOn` when using Reactor operators properly, whereas custom ThreadLocals or bridges to non-Reactor APIs can lose or leak state. Never use `MODE_INHERITABLETHREADLOCAL` on thread pools as a workaround. When integrating non-Reactor async callbacks, pass explicit verified identity/tenant or use vetted context propagation, cleaning up state in `finally`.

### 11.6. Authentication Mono Must Be Cold / Composed

The manager must never call `.subscribe()` on `authMono`. When querying a PIP for roles:

~~~java
return authentication.flatMap(auth ->
        memberships.canRead(auth.getName(), tenant)
                .map(AuthorizationDecision::new))
    .defaultIfEmpty(new AuthorizationDecision(false));
~~~

This snippet sits inside `check` with an already-validated `tenant` variable. Never do:

~~~java
authentication.subscribe(auth -> callExternalPdp(auth));
return Mono.just(new AuthorizationDecision(true)); // severe bug
~~~

That broken fire-and-forget pattern grants access before the PDP even responds and drops cancellation and error propagation.

## 12. Test Matrix for Reactive MethodInvocation

| Scenario | Expected |
| --- | --- |
| Alice has read authority and alpha membership | GRANT alpha resource |
| Bob is only a beta member, requests alpha | DENY, does not query alpha resource |
| Viewer is alpha member without feature authority | DENY |
| Anonymous / empty auth `Mono` | DENY |
| Method signature does not have 2 args | DENY |
| Null/invalid tenant grammar or invalid document ID | DENY |
| Membership `Mono.empty()` | DENY rather than ABSTAIN |
| Membership service error | Fail-closed DENY/error, with metrics |
| Both alpha and beta have document ID 7 | Results never cross-contaminate |
| Resource ID outside tenant | Never leaks data; typically 404 |
| Manager returns `Mono.empty()` directly | Test abstain behavior; never use as deny |
| Annotation/pointcut removed from manager | Negative integration test must fail |
| Methods returning `Mono` and `Flux` | Security runs on subscription; no eager side effects |
| Service self-invocation | Tests detect proxy bypass |
| Context changes Alice→Bob across two subscriptions | Decision matches each `Authentication` |
| Scheduler switch | Reactor Context never leaks via ThreadLocal |
| `.block()` in pipeline | Detect non-blocking violation (e.g., via BlockHound) |
| Membership revoked between two subscriptions | Freshness policy enforced |
| Cached ALLOW missing tenant/principal/action | Tests detect leak |
| PostAuthorize on already-completed external side effect | Must move guard to before-execution |
| Streaming `Flux` has elements from another tenant | Never emit unauthorized items |
| `StepVerifier` test calling Spring proxy | Passes properly vs. manual `new` without advisor |
| HTTP Basic anonymous | 401 per entry point |
| Custom 403 handler / anti-enumeration | Matches API contract; does not disclose records |

### 12.1. Concurrency and Double Subscription

A cold `Mono` can be subscribed to multiple times. If the policy PIP reads membership on every subscription, the outcome can vary with time and `Authentication` context. Calling `.cache()` on a decision without scoping by principal/tenant/action/version risks sharing one GRANT with another request. In particular, never create a global `static Mono<AuthorizationDecision> cachedGrant` for user-dependent decisions.

When retrying a publisher, distinguish re-evaluating the authorization decision from retrying the business operation; avoid unbounded retries or non-idempotent side effects. Monitor cancellation and error signals to avoid leaking resources.

## 13. Common Mistakes

### Mistake 1 — Using the Servlet Interface
`AuthorizationManager<MethodInvocation>` with `Supplier<Authentication>` does not replace `ReactiveAuthorizationManager<MethodInvocation>` in WebFlux. Pick the matching stack and imports.

### Mistake 2 — Mixing Up 6.5 and 7.x API Methods
In 6.5, custom managers implement `check(Mono<Authentication>, MethodInvocation)`; Spring 7 moves to the `authorize` contract. Do not copy a mismatched `check(Supplier<Authentication>, MethodInvocation)` signature from imperative examples.

### Mistake 3 — Using Thread-Local SecurityContextHolder
Reactor Context is not ThreadLocal across schedulers and callbacks. Always consume the `Mono<Authentication>` provided by the framework.

### Mistake 4 — Calling block()
Blocking on the event loop degrades latency, memory, and throughput and can cause deadlocks. Return reactive publishers and compose with `flatMap`.

### Mistake 5 — Returning Mono.empty() When DENY Is Mandatory
Abstain is not an explicit deny. Use `defaultIfEmpty(DENY)` when authentication or PIP results are missing.

### Mistake 6 — Permitting All When the PIP Fails
`onErrorReturn(new AuthorizationDecision(true))` fails open. Use DENY or an appropriate closed error with dedicated logging and metrics.

### Mistake 7 — Trusting tenantId in Method Args as Authorization
Callers can tamper with routes/paths. Server-side membership of the authenticated principal must be checked, and resource queries must be tenant-scoped.

### Mistake 8 — Using Client-Passed userId Instead of Authentication
A method signature `read(String userId, ...)` does not prove the caller is `userId`. Derive the verified principal from Spring Security's `Mono<Authentication>`.

### Mistake 9 — Binding the Advisor to Every Method
Overly broad pointcuts deny unrelated methods or apply the wrong rule. Use a specific marker annotation and test all matching signatures.

### Mistake 10 — Mixing @PreAuthorize and Custom Annotations Without Checking Ordering
Advisors can execute in unexpected order or skip guarding side effects. Verify behavior through a real proxy and favor simple boundaries.

### Mistake 11 — Self-Invocation
`this.read(...)` can bypass AOP. Invoke through a Spring-managed bean, refactor the service, or enforce at an external boundary.

### Mistake 12 — Querying Globally After GRANT
A manager granting `beta` membership must not allow querying `alpha` record ID 7. Repositories must always filter by tenant.

### Mistake 13 — Caching Grants by ID Only
Cache keys must include tenant, actor, action, resource, and relevant revisions; sensitive permissions generally should not cache ALLOWs.

### Mistake 14 — PostAuthorize on Irreversible Side Effects
Post-checks run too late once DB writes or events have fired. Pre-authorization and transaction guards are mandatory.

### Mistake 15 — Unit Testing Only the Manager Without the Proxy
The manager may be right while the advisor is unregistered or the annotation missing. Run `WebTestClient` and `StepVerifier` tests against the proxied bean.

### Mistake 16 — Blocking JPA Inside a Reactive Service
Wrapping blocking I/O in `Mono.just(...)` does not make it async. Use R2DBC/reactive drivers or controlled offloading.

### Mistake 17 — Sharing a Cached Grant Mono Across Users
Publishers can be replayed to other subscribers; if they encapsulate a principal-specific decision, permissions leak. Never memoize authorization globally.

### Mistake 18 — Assuming Method Security Wraps Any Non-Publisher Return Type
Spring reactive method security requires a supported reactive return type to integrate with Reactor Context; use `Mono`/`Flux` (or Kotlin coroutines on supported versions) and test thoroughly.

## 14. Practice Exercises

**Question 1:** Why is `ReactiveAuthorizationManager<MethodInvocation>` different from `ReactiveAuthorizationManager<AuthorizationContext>`?

**Answer:** The former guards method invocations (arguments/target method), while the latter handles reactive HTTP request authorization. The generic type must match what the interceptor/context supplies.

**Question 2:** A manager receives `Mono.empty()` for `Authentication` and returns `Mono.empty()`. Is it guaranteed to deny?

**Answer:** Never assume so. Return `AuthorizationDecision(false)` in mandatory rules to fail closed, and test your specific interceptor version's behavior.

**Question 3:** Is a service returning `Mono.just(repositoryBlocking.findById(...))` truly non-blocking?

**Answer:** No. `repositoryBlocking.findById` runs immediately when evaluating the Java expression to build the `Mono`, before subscription, and also blocks the event loop if called inside the pipeline. Use a reactive driver or controlled offloading.

**Question 4:** Bob has `document:read` but is only a `beta` member. Bob sends `tenant=alpha` and `id=7`. Can he read `Alpha:Budget`?

**Answer:** No. The custom manager checks Bob's `alpha` membership and returns DENY before the service touches data; the repository also enforces tenant-scoped queries.

**Question 5:** Why is `getArguments()` insufficient for determining the principal?

**Answer:** Method arguments are caller inputs and may contain a self-asserted `userId`. The verified principal must come from Spring Security's `Mono<Authentication>`.

**Question 6:** Should you call `authentication.subscribe(...)` and immediately return GRANT?

**Answer:** No. Fire-and-forget detaches authorization from the reactive chain, drops result/exception/cancellation handling, and introduces an authorization race.

**Question 7:** When should you use a custom annotation/manager instead of `@PreAuthorize`?

**Answer:** When Java policy logic is complex, many methods share the same decision, and you want to test/audit the manager centrally. For simple role checks, `@PreAuthorize` is shorter and easier to maintain.

**Question 8:** A request received ALLOW, yet the ACL was revoked before the DB `WRITE`. What must be done?

**Answer:** Revalidate policy/state according to your consistency model, using transactions, locking, or conditional SQL version guards; never treat an earlier ALLOW as permanent permission.

## 15. Implementation Checklist

- [ ] Use compatible Spring Boot/WebFlux and Spring Security versions; verify `check` vs. `authorize` in JavaDoc.
- [ ] Enable `@EnableWebFluxSecurity` and `@EnableReactiveMethodSecurity(useAuthorizationManager=true)`.
- [ ] Public methods on Spring beans return `Mono`/`Flux`; `@TenantRead` marker actually matches the pointcut.
- [ ] Advisor uses `AuthorizationManagerBeforeReactiveMethodInterceptor` with generic `MethodInvocation`, never `AuthorizationContext`.
- [ ] Policy reads `Mono<Authentication>`; never trusts thread-local state or client-passed `userId` as identity.
- [ ] Validate invocation arguments, tenant syntax, IDs, and source membership.
- [ ] Missing or failing `Authentication`/Membership ⇒ explicit DENY, never abstain or fail open.
- [ ] No blocking calls, no manual `subscribe()`; PIP/DB connectors are genuinely reactive.
- [ ] Repositories, caches, and DB queries enforce tenant scoping, plus ownership/ACLs where required.
- [ ] Test 200/401/403/404, identical document IDs across tenants, tenant switching, expired roles, and revocations.
- [ ] Verify Spring proxy/self-invocation, context propagation, repeated subscriptions, and advisor ordering.
- [ ] Protect audit logs, avoid printing tokens/PII, and distinguish policy-denied from service-unavailable.
- [ ] Enforce transaction/freshness controls on protected `WRITE`/`DELETE` operations.
- [ ] Run `WebTestClient` + `StepVerifier` against real context/versions before production.

## 16. Conclusion

`ReactiveAuthorizationManager<MethodInvocation>` bridges **method-level Java context** and **asynchronous, subscriber-scoped authentication**. `MethodInvocation` tells us *which method is called with what arguments*; `Mono<Authentication>` tells us *who the authenticated actor is for this subscription*; a PIP/reactive repository tells us *what permissions the actor holds for that tenant/resource*. Only when all required evidence is valid does the manager emit `AuthorizationDecision(true)`. Missing or invalid state must yield an explicit DENY.

Secure flow:

~~~text
Spring reactive request/context
  -> @TenantRead pointcut
  -> AuthorizationManagerBeforeReactiveMethodInterceptor
  -> ReactiveAuthorizationManager<MethodInvocation>
       -> validated args + Mono<Authentication>
       -> reactive membership/action PIP
       -> GRANT or explicit DENY
  -> tenant-scoped Mono/Flux business publisher
  -> optional object ACL/response policy
  -> safe response and audit
~~~

**Self-check:** If Bob belongs to `beta` and Document ID 7 also exists in `alpha`, is there any path through method args, AOP proxies, caches, Reactor Context, or repositories that lets Bob read `Alpha:Budget`? If so, the reactive method security boundary is not yet complete.

## Official References

- [Spring Security 6.5 – Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html): `@EnableReactiveMethodSecurity`, annotation advice, custom `ReactiveAuthorizationManager<MethodInvocation>`, and Reactor Context.
- [Spring Security 6.5 – ReactiveAuthorizationManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html): `check`/`authorize` and `Mono<Authentication>`; verify your exact minor version.
- [Spring Security 6.5 – AuthorizationManagerBeforeReactiveMethodInterceptor Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/method/AuthorizationManagerBeforeReactiveMethodInterceptor.html): Pointcut/manager constructor and before-method advice.
- [Spring Security 6.5 – PreAuthorizeReactiveAuthorizationManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/method/PreAuthorizeReactiveAuthorizationManager.html): built-in reactive SpEL manager.
- [Spring Security – Reactive SecurityContextHolder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html): Reactor subscriber context.
- [Spring Security – Testing Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/test/method.html): reactive method testing and security context.
- [Spring Framework – AnnotationMatchingPointcut Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/support/annotation/AnnotationMatchingPointcut.html): method annotation pointcuts.
- [Reactor – Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): Context, subscriber-scoped data.
- [Reactor Test – StepVerifier](https://projectreactor.io/docs/test/release/reference/): testing Publisher/`expectNext`/`expectError`.
