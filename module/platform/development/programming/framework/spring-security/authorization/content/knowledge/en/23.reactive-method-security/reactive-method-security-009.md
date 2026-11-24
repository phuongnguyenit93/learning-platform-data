# Limits of `block()`, Manual `subscribe()`, and Tasks Detached from the Processing Chain

> **Module:** Spring Security – Authorization · **Parent topic:** Reactive Method Security. This lesson examines three kinds of "breaking out" of a Reactor chain that commonly cause bugs in WebFlux: calling `block()` to wait synchronously, calling `subscribe()` manually inside the application layer, and launching fire-and-forget tasks with `@Async`/`CompletableFuture`/executors/queues without preserving authorization boundaries. Performance is not the only concern: these patterns can break the **authorize → access data → side effect → report result** order, drop `Authentication` from the Reactor Context, bypass cancellation/backpressure, or mask failures behind HTTP 200. Spring examples use Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring WebFlux, and Reactor 3.x. Verify APIs when migrating to Spring Boot 4 / Spring Security 7.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Explain how **assembly** differs from **subscription** and **completion**, and identify who owns `subscribe()` in a WebFlux HTTP handler.
2. Understand why `Mono.block()`/`Flux.blockLast()` are dangerous on the event loop, and why wrapping blocking APIs in `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` is only a bounded isolation measure.
3. Prove that manual `subscribe()` inside `map`/`doOnNext`/services spawns an independent subscription whose errors, timeouts, cancellation, Reactor Context, and side-effect ordering are no longer governed by the downstream HTTP subscriber.
4. Replace "fire and ignore" with `flatMap`, `concatMap`, `then`, `thenReturn`, or `Mono.when` as appropriate, keeping authorization and operations inside **one unified publisher**.
5. Use `@EnableReactiveMethodSecurity`, `@PreAuthorize`, and `ReactiveSecurityContextHolder` to ensure method security is never bypassed by eager side effects or self-invocation.
6. Build a service with a tenant-specific gate that avoids executing protected writes when denied or unsubscribed and returns proper errors to callers.
7. Distinguish request-bound work from **legitimate detached background jobs**, using a transactional outbox and workers with workload identity, tenant scope, idempotency, retries, and re-authorization.
8. Test cancellation, retries, timeouts, context propagation, exceptions, and double subscriptions using `WebTestClient`/`StepVerifier`.
9. Avoid cached/hot/shared `Mono` instances carrying ALLOW decisions for other actors, and know how `publishOn`/`subscribeOn` interact with Reactor Context.
10. Run a standalone Java 17 example showing how "eager", "detached", and "deferred authorized" produce different outcomes.

## 2. Root Principle: A Method Returning a Publisher Is Not a Completed Task

Reactor typically uses **cold publishers**. Chain-building code describes an operation; most I/O sources begin executing **only when subscribed to**.

~~~text
assemble: controller -> service -> repository -> Mono/Flux returned
subscribe: Spring WebFlux server subscribes to publisher for HTTP response
signals: onSubscribe / request(n) / onNext / onError / onComplete / cancel
~~~

A method:

~~~java
public Mono<Document> read(Long id) {
    return repository.findById(id);
}
~~~

returns a description of the read. It **does not** mean the DB read finished when `return` executed. The WebFlux runtime is the final subscriber for the request, allowing authentication, request cancellation, and pipeline errors to be managed uniformly.

Conversely:

~~~java
public Mono<Document> read(Long id) {
    Document doc = blockingJpaRepository.findById(id).orElseThrow();
    return Mono.just(doc);
}
~~~

executes a blocking lookup **immediately when the Java method runs**, before the publisher is even returned. `Mono.just` does not make prior work asynchronous. If side effects happen before reactive method security advice grants permission, returning a `Mono` cannot "undo" those side effects. Defensive rule: **place all I/O and data mutations behind a cold publisher and a tested authorization boundary**.

### 2.1. Three Moments to Distinguish

| Moment | What Can Happen | Requirement |
| --- | --- | --- |
| Assembly | Java constructs the chain, performs pure side-effect-free input checks | Never query/write protected resources yet |
| Subscription | Framework supplies Reactor Context, activates guards and sources | Authn/authz must precede protected I/O |
| Completion/Error/Cancel | Results, errors, or cancellation propagate through the chain | Never report success before commit/required side effects |

**Note:** Some publishers are hot/eager, already-running futures, cached/shared publishers, or callback APIs with different behavior than cold `Mono.defer`; never assume every `Publisher` is lazy. Verify the semantics of each source.

## 3. `block()`: When Is It Wrong and When Is It an Acceptable Boundary?

`Mono.block()` subscribes to a source and **blocks the current thread** waiting for a value; `Flux.blockFirst()`/`blockLast()` behave similarly. Calls to `toFuture().get()`, `Future.get()`, `Thread.sleep`, and blocking JDBC/JPA/synchronous HTTP clients on the event loop also block even without the word `block`.

Spring WebFlux/Netty uses a small pool of event-loop threads. Blocking one thread stalls other HTTP I/O, driving up latency and causing thread starvation. On Reactor schedulers marked `NonBlocking`, `block()` usually throws an `IllegalStateException` stating blocking is unsupported; elsewhere it may not throw immediately yet remains inappropriate on reactive request paths.

### 3.1. Counterexample: Calling `block()` in a Manager or Controller

~~~java
// WRONG: snippet inside WebFlux/Reactive Method Security.
@PreAuthorize("hasAuthority('document:read')")
public Mono<DocView> read(String tenant, Long id) {
    boolean member = membershipClient.isMember(tenant).block();
    if (!member) {
        return Mono.error(new AccessDeniedException("No membership"));
    }
    return reactiveRepository.findByTenantAndId(tenant, id)
            .map(DocView::from);
}
~~~

Flaws:
- `block()` spawns a second subscription and waits; it may throw on the event loop or stall threads.
- Request security context is **not guaranteed** in the new subscription, especially if downstream operators/sources expect subscriber Context.
- Outer chain timeouts, cancellation, and metrics do not govern the inner subscription cleanly.
- `Boolean` can be `null` on `Mono.empty()`; unboxing `null` triggers unexpected errors outside the contract.
- Running a permission check where the active actor is uncertain is a security risk.

### 3.2. Correct: `flatMap` Keeps Authorization Inside the Pipeline

~~~java
// Snippet in a Spring bean; membershipClient returns Mono<Boolean>.
@PreAuthorize("hasAuthority('document:read')")
public Mono<DocView> read(String tenant, Long id) {
    return membershipClient.isMember(tenant)
            .defaultIfEmpty(false)
            .flatMap(member -> member
                    ? reactiveRepository.findByTenantAndId(tenant, id)
                            .map(DocView::from)
                    : Mono.error(new AccessDeniedException("No membership")));
}
~~~

In a real design, `membershipClient` must verify the **authenticated principal from Reactor Context**, the active tenant, and the action; the method above only illustrates operators and omits full authentication checks. When authorities/tenants require multiple reactive lookups, use `flatMap`/`zipWhen` and fail closed—never `block()`.

### 3.3. If You Must Temporarily Call a Blocking API

Official Reactor pattern:

~~~java
Mono<LegacyResult> wrapped = Mono
        .fromCallable(() -> legacyClient.load(recordId))
        .subscribeOn(Schedulers.boundedElastic());
~~~

- `fromCallable` defers the blocking call until subscription.
- `subscribeOn(boundedElastic)` moves subscribing/running the source onto a **bounded** scheduler for blocking work; it **does not call `subscribe()`** and does not convert a blocking library into non-blocking I/O.
- For downstream operators, results stay within the same chain and errors/cancellations remain reactive signals.
- `boundedElastic` has worker and queue caps: load spikes can fill the queue; configure connection pools, timeouts, concurrency limits, and observability.
- An in-flight blocking call may not interrupt or roll back immediately when downstream cancels. Never promise that cancel equals an undone DB write.
- Place `subscribeOn` close to the `fromCallable` source so preceding blocking work does not accidentally run on the event loop.

**Never use `Schedulers.parallel()` or `Schedulers.single()` for blocking I/O**, as those schedulers are intended for non-blocking work. The long-term fix for DB/HTTP is reactive drivers (R2DBC, `WebClient`, etc.) when architecturally justified; `boundedElastic` is a bridge.

### 3.4. Not Every `block()` Is Strictly Forbidden

At **imperative boundaries that explicitly own their lifecycle**—such as CLI `main`, migration scripts, or certain JUnit tests outside the event loop—`block(Duration)` can be reasonable. There, thread, deadline, and exception handling are explicit; never place it in WebFlux controllers, reactive services/method-security managers, or pipelines expected to stay non-blocking. In reactive tests, `StepVerifier` usually expresses semantics much more clearly than `block()`.

## 4. Manual `subscribe()`: Why One Small Call Causes Four Kinds of Lost Control

Counterexample:

~~~java
// WRONG: assume publishAudit returns Mono<Void>.
public Mono<Receipt> approve(Command command) {
    return permissionGuard(command)
            .then(saveApproval(command))
            .doOnNext(saved -> publishAudit(saved).subscribe());
}
~~~

`doOnNext` does not wait for the publisher returned by `publishAudit`. `.subscribe()` starts a **separate** subscription right inside the callback. Consequences:
1. The HTTP response can finish before auditing succeeds or fails.
2. Audit exceptions never propagate into the outer `Mono<Receipt>` contract; they may be dropped or logged without correlation.
3. If the client cancels the request, the detached audit keeps running; if it ought to cancel with the request, that link is broken.
4. The new subscriber's Reactor Context / `SecurityContext` is not guaranteed to match the parent publisher; `tenant`/`Authentication` values can go missing or copy improperly.

This is dangerous whenever "audit" is actually an authorization check, payment capture, access-key delivery, outbox write, or mandatory domain event. **Never return HTTP 200 while mandatory work remains an unmonitored fire-and-forget task.**

### 4.1. Correct: One Publisher for All Mandatory Work

~~~java
public Mono<Receipt> approve(Command command) {
    return permissionGuard(command)
            .then(saveApproval(command))
            .flatMap(saved ->
                    publishAudit(saved).thenReturn(saved));
}
~~~

`flatMap` awaits the inner publisher through reactive composition. `thenReturn(saved)` emits the receipt only if auditing finishes successfully; audit errors propagate up the outer chain. No `subscribe()` is needed in the service. The WebFlux runtime subscribes to the final publisher for the HTTP response.

If you need **DB mutations and outbox events to commit together**, merely sequencing two `Mono`s is insufficient because the database transaction may already have committed before `publishAudit`. Use a transactional outbox or a true reactive transaction spanning shared persistence, then dispatch events post-commit.

### 4.2. `doOnNext`/`doOnSuccess` Are Not Places for Async Business Operations

~~~java
// WRONG: result Mono of asyncAction is ignored.
return repository.save(doc)
        .doOnNext(saved -> asyncAction(saved));

// Also WRONG: subscribing to "force it to run":
return repository.save(doc)
        .doOnNext(saved -> asyncAction(saved).subscribe());
~~~

`doOnNext` suits **lightweight synchronous side effects** such as incrementing a counter or writing redacted logs. It does not compose another `Mono`. `Mono.doOnSuccess` can also receive `null` when a `Mono` completes empty, requiring careful semantics. For async work, use `flatMap`/`concatMap`/`then`.

### 4.3. Which Operator Fits Which Scenario?

| Intent | Typically Appropriate Operator | Meaning |
| --- | --- | --- |
| Check permission then run logic without guard's value | `guard.then(work)` | Waits for guard completion; errors halt chain |
| Save record, send audit, and return saved record | `save.flatMap(x -> audit(x).thenReturn(x))` | Awaits audit before emitting `x` |
| Find resource then update using value | `find.flatMap(this::update)` | Composes publisher per item |
| Process event stream sequentially in order | `Flux.concatMap(this::handle)` | Preserves ordering and sequential execution |
| Independent tasks, all must succeed | `Mono.when(a, b)` | Waits for all sources; watch transaction bounds |
| Return response after chain finishes | `thenReturn(response)` | Emits after completion |
| Abort if deadline exceeded | `timeout(Duration)` | Emits timeout error; committed side effects do not roll back |
| Handle errors conditionally | `onErrorResume(...)` | Never swallow `AccessDenied` into ALLOW |
| Add lightweight logging | `doOnEach(...)` | Can read signal/context; never call async subscribe inside |

**Never assume `Mono.when` guarantees "no side effects if one source fails"**: sources can run concurrently. When authorization must precede every write, use `guard.then(work)`, never `Mono.when(guard, work)` because `work` may start before `guard` succeeds.

## 5. Special Hazards in Reactive Method Security

Spring Security reactive method security reads Reactor Context via `ReactiveSecurityContextHolder`. `@EnableReactiveMethodSecurity(useAuthorizationManager=true)` integrates method authorization with `Publisher` return types such as `Mono`/`Flux`. When a method is invoked through a **Spring-managed proxy**, advisors intercept before or after execution depending on annotations and configuration.

Counterexample:

~~~java
// WRONG: protected side effect already started while building the method return.
@PreAuthorize("hasAuthority('document:write')")
public Mono<Void> delete(Long id) {
    externalBlockingClient.deleteNow(id); // eager I/O
    return Mono.empty();
}
~~~

Even if the current version's interceptor defers method invocation properly, such side effects couple correctness to AOP/assembly details instead of guaranteeing safety inside the `Publisher`. Refactor so all effects live behind the guard inside lazy sources, verified with deny tests:

~~~java
@PreAuthorize("hasAuthority('document:write')")
public Mono<Void> delete(Long id) {
    return Mono.defer(() ->
            reactiveRepository.deleteById(id));
}
~~~

This snippet **omits** object/tenant authorization; production must check actor, tenant, resource scope, and transactions before deleting. Replace global `deleteById` with tenant-scoped queries whenever IDs do not inherently guarantee tenant isolation.

### 5.1. Method Args Are Not the Authenticated Principal

~~~text
read(tenant="beta", id=7)
~~~

`tenant` is merely a caller-mutable selector. In WebFlux, extract authentication from `ReactiveSecurityContextHolder.getContext()` or the `Mono<Authentication>` supplied by the reactive interceptor, then verify membership and roles for that tenant. Never trust raw `userId`, `role`, or `isOwner` parameters as authorization. A `ReactiveAuthorizationManager<MethodInvocation>` can validate both method args and the authenticated actor asynchronously before granting access.

### 5.2. Self-Invocation Bypasses the Proxy

~~~java
@Service
class DemoService {
    public Mono<String> outer() {
        return this.securedInner(); // risk of bypassing Spring AOP advice
    }

    @PreAuthorize("hasAuthority('admin')")
    public Mono<String> securedInner() {
        return Mono.just("protected");
    }
}
~~~

Under standard proxy-based Spring AOP, `this.securedInner()` does not pass through the proxy. If `outer` is exposed without equivalent protection, the annotation on the inner method may not run. Split out the secured service bean, invoke via Spring proxies, and test the real bean—never "fix" it with manual `subscribe()`.

### 5.3. Returning a Publisher Is Crucial

In Java reactive method security, guarded methods should return supported reactive types (`Mono`/`Flux`). Returning a plain object or `void` while calling `.subscribe()` internally leaves the framework with no result `Publisher` to compose and enforce per subscriber. Kotlin coroutines have separate version/config support; verify your dependency's documentation.

### 5.4. Reactor Context Is Not ThreadLocal

~~~java
// WRONG when used for identity inside any reactive pipeline:
Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();
~~~

In WebFlux, Reactor Context belongs to the **subscriber**, not permanently to a thread. `publishOn`/`subscribeOn` can switch threads while Reactor Context still flows through compliant operators, whereas raw `ThreadLocal` or separate `@Async` threads do not automatically receive identity. Read it properly:

~~~java
Mono<String> currentUser =
        ReactiveSecurityContextHolder.getContext()
                .map(context -> context.getAuthentication().getName());
~~~

This snippet assumes a `SecurityContext` exists; production code must deny on empty/anonymous contexts and avoid exposing usernames in logs unnecessarily.

### 5.5. Never Manually Subscribe to the Auth Mono in a Custom Manager

~~~java
// WRONG: snippet inside ReactiveAuthorizationManager.
authentication.subscribe(a -> loadMembership(a.getName()));
return Mono.just(new AuthorizationDecision(true));
~~~

This **grants access before membership finishes loading**—a classic TOCTOU / fail-open flaw. Compose instead:

~~~java
return authentication
        .flatMap(auth -> memberships.canRead(auth.getName(), tenant)
                .map(AuthorizationDecision::new))
        .defaultIfEmpty(new AuthorizationDecision(false));
~~~

This snippet assumes `tenant` is already validated, `memberships` uses a trusted source, and the manager signature matches your API version. Never paste standalone snippets without caller constraints. On membership errors, return DENY or fail closed—never `onErrorReturn(new AuthorizationDecision(true))`.

## 6. Spring Boot WebFlux Application: All Mandatory Steps in One Chain

This demo uses:
- In-memory HTTP Basic users for learning (never use `{noop}` passwords in production).
- HTTP GET authentication gate; method-level `@PreAuthorize` checks feature authorities.
- Tenant-specific memberships from a **server-managed map** to prevent client spoofing.
- Composite-key store `(tenant, documentId)` where two tenants share ID `7`.
- `read` and `rename` service methods returning cold `Publisher`s with zero `block()` or `subscribe()` calls.
- `rename` as a side-effecting business method verifying **no writes occur before subscribe**, and denied callers trigger zero writes. It exposes no HTTP mutation route in the demo to keep CSRF simple; mutations are tested via `StepVerifier` against the bean proxy.

Files:
~~~text
src/main/java/demo/reactive/ReactiveBoundaryApplication.java
src/test/java/demo/reactive/ReactiveBoundaryApplicationTest.java
~~~

### 6.1. Complete Application Code

Save `src/main/java/demo/reactive/ReactiveBoundaryApplication.java`:

~~~java
package demo.reactive;

import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
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

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class ReactiveBoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveBoundaryApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http.authorizeExchange(ex -> ex
                    .pathMatchers("/api/tenants/**").authenticated()
                    .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
        // GET only, do not disable CSRF arbitrarily.
    }

    @Bean
    MapReactiveUserDetailsService users() {
        return new MapReactiveUserDetailsService(
                User.withUsername("alice")
                    .password("{noop}demo")
                    .authorities("document:read", "document:write")
                    .build(),
                User.withUsername("bob")
                    .password("{noop}demo")
                    .authorities("document:read", "document:write")
                    .build(),
                User.withUsername("viewer")
                    .password("{noop}demo")
                    .authorities("profile:read")
                    .build());
    }
}

record DocKey(String tenant, long id) {}
record Doc(long id, String tenant, String title) {}
record DocView(long id, String tenant, String title) {}

@Component
class TenantMemberships {
    private final Map<String, Map<String, Set<String>>> rights = Map.of(
            "alice", Map.of("alpha", Set.of("READ", "WRITE")),
            "bob", Map.of("beta", Set.of("READ")),
            "viewer", Map.of("alpha", Set.of("READ")));

    Mono<Boolean> has(String principal, String tenant, String action) {
        return Mono.defer(() -> Mono.just(
                rights.getOrDefault(principal, Map.of())
                    .getOrDefault(tenant, Set.of())
                    .contains(action)));
    }
}

@Component
class DocStore {
    private final ConcurrentMap<DocKey, Doc> data =
            new ConcurrentHashMap<>(Map.of(
                new DocKey("alpha", 7L),
                    new Doc(7L, "alpha", "ALPHA:Budget"),
                new DocKey("beta", 7L),
                    new Doc(7L, "beta", "BETA:Budget"),
                new DocKey("alpha", 8L),
                    new Doc(8L, "alpha", "ALPHA:Notes")));

    private final AtomicInteger writeCount = new AtomicInteger();

    Mono<Doc> findWithinTenant(String tenant, Long id) {
        return Mono.defer(() ->
                Mono.justOrEmpty(data.get(new DocKey(tenant, id))));
    }

    Mono<Doc> rename(String tenant, Long id, String newTitle) {
        // Mutation runs on SUBSCRIBE, not when creating the Mono.
        return Mono.defer(() -> {
            Doc changed = data.computeIfPresent(
                    new DocKey(tenant, id),
                    (key, old) -> new Doc(
                            old.id(), old.tenant(), newTitle));
            if (changed != null) {
                writeCount.incrementAndGet();
            }
            return Mono.justOrEmpty(changed);
        });
    }

    int writes() {
        return writeCount.get();
    }
}

@Service
class DocumentService {
    private final TenantMemberships memberships;
    private final DocStore store;

    DocumentService(TenantMemberships memberships, DocStore store) {
        this.memberships = memberships;
        this.store = store;
    }

    private Mono<Void> requireTenantAction(String tenant, String action) {
        if (tenant == null
                || !tenant.matches("[a-z][a-z0-9-]{0,31}")) {
            return Mono.error(new AccessDeniedException("Invalid tenant"));
        }

        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .switchIfEmpty(Mono.error(
                        new AccessDeniedException("No Authentication")))
                .flatMap(auth -> {
                    if (auth == null || !auth.isAuthenticated()
                            || auth instanceof AnonymousAuthenticationToken) {
                        return Mono.<Void>error(
                                new AccessDeniedException("Unauthenticated"));
                    }
                    return memberships.has(auth.getName(), tenant, action)
                            .defaultIfEmpty(false)
                            .flatMap(allowed -> allowed
                                    ? Mono.<Void>empty()
                                    : Mono.<Void>error(
                                            new AccessDeniedException(
                                                "Tenant/action denied")));
                }).then();
    }

    @PreAuthorize("hasAuthority('document:read')")
    public Mono<DocView> read(String tenant, Long id) {
        if (id == null || id <= 0) {
            return Mono.error(new AccessDeniedException("Invalid ID"));
        }
        return requireTenantAction(tenant, "READ")
                .then(store.findWithinTenant(tenant, id))
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(HttpStatus.NOT_FOUND)))
                .map(d -> new DocView(
                        d.id(), d.tenant(), d.title()));
    }

    @PreAuthorize("hasAuthority('document:write')")
    public Mono<DocView> rename(
            String tenant, Long id, String newTitle) {
        if (id == null || id <= 0 || newTitle == null
                || newTitle.isBlank() || newTitle.length() > 180) {
            return Mono.error(new AccessDeniedException("Invalid input"));
        }
        return requireTenantAction(tenant, "WRITE")
                .then(store.rename(tenant, id, newTitle))
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(HttpStatus.NOT_FOUND)))
                .map(d -> new DocView(
                        d.id(), d.tenant(), d.title()));
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

**Scope of the example:**
- Spring WebFlux receives HTTP requests; `@PreAuthorize` enforces feature authorities via the Spring-managed service proxy.
- `requireTenantAction` reads `Authentication` from the subscriber's Reactor Context; the in-memory membership map is a demo PIP.
- `Mono.defer` keeps both reads and writes lazy. There is not a single `subscribe()` or `block()` in the application service.
- `then(store.rename(...))` executes the write only if the authorization chain **completes successfully**. If `requireTenantAction` returns `Mono.error(AccessDeniedException)`, the store receives no subscription.
- Two tenants share ID 7, yet `DocKey(tenant, id)` keeps them isolated.
- `writeCount` verifies side effects occur only after an authorized subscription.
- `rename` **does not** expose HTTP `PATCH`/`POST` to avoid CSRF complexity in the example; in production, HTTP mutations require proper CSRF protection when using cookie/browser credentials, transaction-aligned authorization, optimistic versions, and tenant predicates.
- There is no object-specific ACL; if users within the same tenant may read only a subset, add ACL/owner checks before returning content.
- `{noop}` passwords and plain HTTP are strictly for local demos; production requires HTTPS and secure password hashing / token validation.
- In production, use R2DBC/reactive stores or controlled blocking isolation; an in-memory map does not replace `WHERE tenant_id=:tenant` queries.

### 6.2. Gradle Dependencies

In a project already configured with the Spring Boot Gradle plugin/dependency management and Java 17+:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

This is only the `dependencies` block, not a full `build.gradle`. The sample omits the MVC starter; when WebFlux and MVC coexist on the classpath, Spring Boot's web-application-type rules must be managed carefully. Test classes below target Boot 3.x.

### 6.3. Testing HTTP

~~~bash
./gradlew bootRun

curl --user alice:demo http://localhost:8080/api/tenants/alpha/documents/7
curl --user bob:demo http://localhost:8080/api/tenants/beta/documents/7
curl --user bob:demo http://localhost:8080/api/tenants/alpha/documents/7
curl --user viewer:demo http://localhost:8080/api/tenants/alpha/documents/7
~~~

Expected:
- Alice→alpha/7: 200 with `ALPHA:Budget`.
- Bob→beta/7: 200 with `BETA:Budget`.
- Bob→alpha/7: 403 due to membership.
- Viewer→alpha/7: 403 due to missing feature authority.
- Anonymous: HTTP Basic typically returns 401.

This is a local experiment; never send Basic credentials over public HTTP. Before production, configure TLS/JWT/sessions matching your threat model.

## 7. Integration Tests: Authorization, Laziness, and Zero Detached Side Effects

Create `src/test/java/demo/reactive/ReactiveBoundaryApplicationTest.java`:

~~~java
package demo.reactive;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class ReactiveBoundaryApplicationTest {
    @Autowired WebTestClient client;
    @Autowired DocumentService service; // Spring-managed AOP proxy.
    @Autowired DocStore store;

    private Authentication actor(String username, String authority) {
        return UsernamePasswordAuthenticationToken.authenticated(
                username, "unused",
                List.of(new SimpleGrantedAuthority(authority)));
    }

    @Test
    void authorizedAlphaAndBetaSameIdNeverMix() {
        client.get().uri("/api/tenants/alpha/documents/7")
                .headers(h -> h.setBasicAuth("alice", "demo"))
                .exchange().expectStatus().isOk()
                .expectBody().jsonPath("$.title")
                .isEqualTo("ALPHA:Budget");

        client.get().uri("/api/tenants/beta/documents/7")
                .headers(h -> h.setBasicAuth("bob", "demo"))
                .exchange().expectStatus().isOk()
                .expectBody().jsonPath("$.title")
                .isEqualTo("BETA:Budget");
    }

    @Test
    void unauthorizedRequestDoesNotReadAcrossTenant() {
        client.get().uri("/api/tenants/alpha/documents/7")
                .headers(h -> h.setBasicAuth("bob", "demo"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void viewerLacksFeatureAuthority() {
        client.get().uri("/api/tenants/alpha/documents/7")
                .headers(h -> h.setBasicAuth("viewer", "demo"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void noSubscriptionMeansNoProtectedWrite() {
        Authentication alice = actor("alice", "document:write");
        Mono<DocView> action =
                service.rename("alpha", 7L, "ALPHA:Updated")
                        .contextWrite(
                          ReactiveSecurityContextHolder.withAuthentication(
                                  alice));

        assertEquals(0, store.writes()); // assembly does not write.
        StepVerifier.create(action)
                .expectNextMatches(v ->
                        v.title().equals("ALPHA:Updated"))
                .verifyComplete();
        assertEquals(1, store.writes()); // writes only after subscribe and GRANT.
    }

    @Test
    void deniedTenantWriteNeverTouchesStore() {
        // Bob has global document:write, yet beta membership is READ-only.
        Authentication bob = actor("bob", "document:write");
        Mono<DocView> action =
                service.rename("beta", 7L, "BETA:Forbidden")
                        .contextWrite(
                          ReactiveSecurityContextHolder.withAuthentication(
                                  bob));

        StepVerifier.create(action)
                .expectError(AccessDeniedException.class)
                .verify();
        assertEquals(0, store.writes());
    }

    @Test
    void missingReactiveAuthenticationDeniesWrite() {
        StepVerifier.create(
                service.rename("alpha", 7L, "ALPHA:Forbidden"))
                .expectError(AccessDeniedException.class)
                .verify();
        assertEquals(0, store.writes());
    }

    @Test
    void invalidInputDoesNotMutate() {
        Authentication alice = actor("alice", "document:write");
        StepVerifier.create(
                service.rename("alpha", -1L, "Bad")
                        .contextWrite(
                           ReactiveSecurityContextHolder.withAuthentication(
                                   alice)))
                .expectError(AccessDeniedException.class)
                .verify();
        assertEquals(0, store.writes());
    }
}
~~~

`WebTestClient` tests hit the reactive server; `StepVerifier` invokes the **Spring-injected service proxy** with `Authentication` attached to the subscriber context. Replacing the service with `new DocumentService(...)` skips AOP and can give false passes where method security never ran. `@DirtiesContext` isolates in-memory state per test; larger suites can reset fixtures directly for speed.

### 7.1. Why Is Testing "Without Subscribing" Especially Valuable?

A common bug is updating the DB during assembly:

~~~java
// COUNTEREXAMPLE:
Doc changed = storeBlocking.renameNow(tenant, id, title);
return Mono.just(changed);
~~~

Tests asserting only "after subscribing, the value is right" can miss that the write ran **before subscription and authorization**. `noSubscriptionMeansNoProtectedWrite` tests the invariant directly: assembling the `Mono` and attaching Reactor Context makes zero store changes. Only after `StepVerifier` subscribes with valid permissions does exactly one write occur.

### 7.2. Testing Cancellation and Timeouts: Do Not Expect Magical Rollbacks

If a producer has not started side effects yet, cancellation must prevent downstream work from subscribing/continuing; however, if a DB transaction has already committed, cancellation cannot automatically reverse it. For reliable cancellation tests, place a delayed gate using `Mono.delay`/`TestPublisher`/virtual time and cancel **before the side-effect stage subscribes**, verifying counters and event ordering. Never call `thenCancel()` on an immediately synchronous source and claim the write did not run: the source may finish before cancellation arrives.

~~~java
// Standalone test snippet: protected work sits AFTER an uncompleted gate.
var gate = new reactor.test.publisher.TestPublisher<Void>();
var writes = new java.util.concurrent.atomic.AtomicInteger();

Mono<Void> sequence = gate.mono()
        .then(Mono.fromRunnable(writes::incrementAndGet));

StepVerifier.create(sequence)
        .thenCancel()
        .verify();

// Because gate has not completed yet, downstream effect has not run:
assertEquals(0, writes.get());
~~~

This is only a JUnit test snippet, not application code. With `TestPublisher<Void>`, check your exact API/compiler version, or use `Mono.never()` if you only need a gate that never completes. Cancellation tests should verify separately that external tasks stop running, resources are released, and already-committed events handle idempotency cleanly.

### 7.3. Testing Context Loss with Two Subscriptions

When the same publisher is subscribed to as Alice and then Bob, permissions must evaluate **per subscriber**, never via a static cached grant:

~~~java
// Snippet: same Spring proxy, two different Authentication contexts.
Mono<DocView> source = service.read("alpha", 7L);

StepVerifier.create(source.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(alice)))
        .expectNextCount(1).verifyComplete();

StepVerifier.create(source.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(bob)))
        .expectError(AccessDeniedException.class).verify();
~~~

Here `alice`/`bob` are test-built authenticated tokens matching their authorities and tenant memberships. Never apply `source.cache()` or `share()` globally over a per-user `Publisher`, as an earlier subscriber's ALLOW can be replayed to another subscriber if cached at the wrong layer.

## 8. Detached Tasks: Which Must Wait and Which Can Run in the Background?

Separate business contracts clearly:

| Task Type | Must Finish Before HTTP Success? | Design |
| --- | --- | --- |
| Authorization for read/write | **Mandatory** | Compose into the chain before protected data |
| Primary DB update of the request | **Mandatory** | Compose with transactions and clear result/error |
| Synchronously required compliance audit | Usually mandatory, or durable evidence before success | Compose into transaction/outbox |
| "Must eventually publish" domain event | Needs durable evidence before success | Transactional outbox with DB commit |
| Post-processing email notification, retryable | Can detach **after durable event** | Outbox + worker |
| Optional cache warmup | Can detach with clear owner/lifecycle | Scheduled/background service, bounded concurrency |
| Non-sensitive analytics/telemetry | Can run async via managed pipeline | Metrics/tracing SDK, no raw PII |
| Payments / token or privilege issuance | Never simple fire-and-forget | Domain transaction/state machine + idempotency |

### 8.1. Counterexample: Fire-and-Forget Inside HTTP

~~~java
// WRONG:
public Mono<Response> submit(Request request) {
    reactiveAuthorization(request)
            .subscribe();  // discards decision result

    save(request)
            .subscribe();  // write runs independently and may start early

    return Mono.just(new Response("accepted"));
}
~~~

Risks: `save` may run before authorization, HTTP succeeds even if `save` fails, exceptions never reach the caller, cancellation has no effect, and security context is not properly wired to the two new subscriptions.

### 8.2. Correct: Synchronizing All Mandatory Conditions in One Chain

~~~java
public Mono<Response> submit(Request request) {
    return reactiveAuthorization(request)
            .then(save(request))
            .flatMap(saved ->
                    auditPersist(saved).thenReturn(saved))
            .map(saved -> new Response("completed"));
}
~~~

Each call is assumed to return a cold `Mono`; if `reactiveAuthorization` can complete empty to indicate "no decision", `then(save)` would still execute. Therefore **authorization guards must convert deny/unknown/empty into `Mono.error(AccessDeniedException)`**, never using empty completion to mean DENY. Never chain `then` directly after a `Mono<Boolean>` authorization decision without checking the boolean:

~~~java
// WRONG: Boolean false still completes normally, so THEN still runs.
return canWrite(tenant).then(save(doc));
~~~

Right approach:

~~~java
return canWrite(tenant)
        .defaultIfEmpty(false)
        .flatMap(allowed -> allowed
                ? Mono.<Void>empty()
                : Mono.<Void>error(new AccessDeniedException("Denied")))
        .then(save(doc));
~~~

This is critical whenever a policy service returns `Mono.empty()` for undecided outcomes.

### 8.3. Transactional Outbox: Background Work Can Detach Without Being Forgotten

When you must update a DB and emit an event to a queue/broker, prefer:

~~~text
HTTP request subscription
  -> authenticated actor + tenant/action verification
  -> DB transaction:
       UPDATE tenant-scoped business row
       INSERT outbox_event(tenant, actor, type, id, payload, version)
  -> COMMIT
  -> HTTP 202/200 per contract
  ...
  -> outbox dispatcher (monitored) publishes broker event
  -> consumer authenticates producer + tenant scope
  -> revalidates rights/resource state when domain requires
  -> idempotent processing + retry/DLQ + audit
~~~

Writing the outbox row inside the same transaction as the domain mutation guarantees **durable intent to publish** (not end-to-end exactly-once delivery). Publishers and consumers can retry or duplicate deliveries, requiring idempotency keys and at-least-once semantics. Never equate "wrote to outbox" with "email delivered / payment settled". API contracts must distinguish `ACCEPTED`, `PENDING`, and `COMPLETED`.

### 8.4. Who Owns Background Subscriptions?

`subscribe()` is not universally forbidden. A **lifecycle-owning component**—such as a Spring-managed queue consumer, scheduled worker, application startup runner, or controlled Reactor `Flux`—can legitimately act as a subscriber. That component must:
- Authenticate its own workload/service identity rather than blindly borrowing an already-completed HTTP request's authentication.
- Verify tenant/action/resource permissions for the running job; the actor's membership may have been revoked.
- Track the `Disposable`/subscription to stop/cancel cleanly on shutdown, handling errors, retries, backpressure, health/metrics, and resource cleanup.
- Enforce concurrency limits, idempotency, DLQs, correlation IDs, and auditing.
- Never report `COMPLETED` when work has merely been scheduled.
- Never pin a user's `SecurityContext` into a static global or indefinite queue.

**Boundary:** libraries/services returning `Mono` to callers are responsible for **composing**, while true lifecycle owners do the subscribing. That keeps decisions over when to execute, time out, cancel, and report success in one clear place.

## 9. `@Async`, `CompletableFuture`, Executors, and Reactor Context

Bad example:

~~~java
@PreAuthorize("hasAuthority('document:write')")
public Mono<String> startJob(String tenant, Long id) {
    CompletableFuture.runAsync(() -> {
        // Task detached from Reactor Context/request lifecycle.
        legacyWriter.write(tenant, id);
    });
    return Mono.just("OK");
}
~~~

A `CompletableFuture` can start immediately at assembly before the request finishes policy checks, run on another thread pool without `SecurityContext`, fail silently, and outlive HTTP cancellation. `@Async` likewise switches execution contexts and does not safely copy Reactor Context/authentication across all topologies.

### 9.1. Offloading Blocking Work While Staying Within the Request

~~~java
public Mono<LegacyResult> readLegacy(Long id) {
    return reactiveAuthorizationFor(id)
            .then(Mono.fromCallable(() ->
                    blockingLegacyClient.read(id))
                    .subscribeOn(Schedulers.boundedElastic()));
}
~~~

This snippet assumes `reactiveAuthorizationFor(id)` returns a `Mono<Void>` that **errors on DENY**, not an unchecked `Mono<Boolean>`. The task remains part of the request chain: errors, cancellations, and timeouts flow as Reactor signals. Still, blocking calls may not abort immediately upon cancel; enforce client/socket timeouts, thread-pool caps, and consistency contracts.

### 9.2. When You Must Dispatch to a Queue

Never push a full `Authentication`, raw JWT, cookie, or cached ALLOW as a "permanent authorization pass". Minimal event envelope:

~~~json
{
  "eventId": "evt-041",
  "tenantId": "alpha",
  "actorId": "opaque-user-17",
  "action": "GENERATE_REPORT",
  "resourceId": "doc-7",
  "schemaVersion": 1,
  "correlationId": "request-391"
}
~~~

This is illustrative data. Workers trust messages only after producer authentication/integrity checks, enforce permissions against job identity/actor policies and fresh state, and cap retries/timeouts. Dedicated service principals and tightly governed "delegated actor" rules may be used; never assume a user authorized at `t1` still holds permission at `t2`.

### 9.3. Does Reactor Context Survive `publishOn`/`subscribeOn`?

With standard Reactor operators, Context binds to the subscriber and propagates within the same chain across scheduler switches. However, **`ThreadLocal` does not automatically become Reactor Context**, nor does Context magically jump into an external `CompletableFuture.runAsync` task outside the chain. Context-propagation/automatic modes can bridge select values depending on version and setup, yet they never rescue a detached subscription running under the wrong identity or authorization scope.

## 10. Timeouts, Cancellation, Retries, and HTTP Outcomes

### 10.1. `timeout()` Is Not a Rollback

~~~java
return authorize()
        .then(writeToDatabase())
        .timeout(Duration.ofSeconds(2));
~~~

When the deadline expires, the outer publisher emits a timeout error and cancels upstream. If the DB already committed before cancellation arrived, data has changed. Enforce idempotency, transactions, retry policies, and reconciliation; never treat an HTTP 504/timeout as proof that "the write definitely did not happen".

### 10.2. Retries Must Never Authorize Using Stale Results

If `retryWhen` wraps the whole chain, authorization re-runs; if you retry only the business write after a single ALLOW, membership could change between attempts. Choose according to your risk model. Sensitive `WRITE`/`DELETE` operations need rechecks or transaction-guarded consistency. Never retry infinitely or retry non-idempotent side effects without an idempotency key.

### 10.3. Cancellation Can Be Broken by Manual `subscribe()`

~~~text
outer request subscribes
 -> authorized and starts work
 -> client disconnects, outer subscription cancelled
 -> child started by service.subscribe(): still running
 -> child may write or emit secret with no active owner
~~~

For mandatory request tasks, clear cancellation semantics still cannot undo a committed write; for background tasks meant to outlive the request, move them to a durable queue/outbox and **document that they run independently**. Never leave half-detached state behind an unmanaged `subscribe()`.

### 10.4. `doFinally` and Cleanup

`doFinally(signalType -> ...)` runs on `onComplete`/`onError`/`cancel`; it works well for synchronous metrics/cleanup, yet you should not call `.subscribe()` on a mandatory reactive audit inside it. For reactive resources, use `usingWhen` or reactive transaction boundaries to release asynchronously within the same composition. Cleanup failures need an explicit error/compensation contract rather than vanishing into logs.

## 11. Standalone Java 17: Eager, Detached, and Deferred

You do not need Spring or Reactor to grasp ordering bugs. The program below uses Java 17 `Supplier` and `Runnable` as a simple model. **It does not simulate Reactor Context, non-blocking I/O, or Spring method advisors.** It highlights the difference between:
- Eager side effects running before permission checks.
- Detached tasks triggered outside the authorization path.
- Deferred suppliers checking permissions before running side effects when executed.

Save `AuthorizedLifecycleDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

public class AuthorizedLifecycleDemo {
    record Actor(String name, boolean allowed) {}

    private static final AtomicInteger WRITES = new AtomicInteger();

    static Supplier<String> authorizedWrite(Actor actor) {
        // Like "assembly" step: only creates description.
        return () -> {
            if (actor == null || !actor.allowed()) {
                return "DENY";
            }
            WRITES.incrementAndGet();
            return "GRANT";
        };
    }

    static String eagerWriteThenCheck(Actor actor) {
        WRITES.incrementAndGet();  // Side effect already happened!
        return actor != null && actor.allowed()
                ? "GRANT" : "DENY_TOO_LATE";
    }

    static Runnable detachedTask() {
        return WRITES::incrementAndGet;
    }

    public static void main(String[] args) {
        Actor alice = new Actor("alice", true);
        Actor bob = new Actor("bob", false);

        Supplier<String> lazy = authorizedWrite(alice);
        System.out.println("before-run=" + WRITES.get());

        System.out.println("denied=" + authorizedWrite(bob).get());
        System.out.println("after-deny=" + WRITES.get());

        System.out.println("allowed=" + lazy.get());
        System.out.println("after-allow=" + WRITES.get());

        System.out.println("eager-denied=" + eagerWriteThenCheck(bob));
        System.out.println("after-eager=" + WRITES.get());

        Runnable task = detachedTask();
        task.run();  // Never checks actor/tenant!
        System.out.println("after-detached=" + WRITES.get());

        System.out.println("missing-auth=" + authorizedWrite(null).get());
        System.out.println("final-writes=" + WRITES.get());
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 AuthorizedLifecycleDemo.java
java AuthorizedLifecycleDemo
~~~

**Exact stdout:**

~~~text
before-run=0
denied=DENY
after-deny=0
allowed=GRANT
after-allow=1
eager-denied=DENY_TOO_LATE
after-eager=2
after-detached=3
missing-auth=DENY
final-writes=3
~~~

Explanation:
- `authorizedWrite(alice)` when creating the `Supplier` **does not increment** the counter; only `.get()` runs it.
- Bob is denied before the side effect, so the counter stays unchanged.
- `eagerWriteThenCheck(bob)` returns DENY after the side effect already ran: checking too late cannot erase a write.
- `detachedTask().run()` illustrates an independent task with no authorization check. In Reactor, an internal `subscribe()` creates an analogous detached boundary.
- `authorizedWrite(null)` fails closed.

### 11.1. Key Differences from Reactor

JDK `Supplier#get()` does not support cancellation, backpressure, schedulers, Context, or async errors like `Mono`. It only demonstrates **ordering**. Never replace `Mono` with `Supplier` in production WebFlux. In a reactive server, the runtime is the subscriber and Spring method security decides using the subscription's Reactor Context.

## 12. Subtle Traps Where Operators Look Right

### 12.1. `Mono.just(blockingCall())` Is Not Lazy

~~~java
return Mono.just(jdbcDao.load(id));  // load runs eagerly.
~~~

Correct when temporarily wrapping blocking calls:

~~~java
return Mono.fromCallable(() -> jdbcDao.load(id))
        .subscribeOn(Schedulers.boundedElastic());
~~~

Or use a genuine reactive repository. Note that a `null` return from `Callable` produces an empty `Mono`; if `null` means "no decision", convert it to an explicit DENY.

### 12.2. `Mono.defer` Whose Callback Calls `subscribe()`

~~~java
return Mono.defer(() -> {
    auditMono.subscribe(); // still detached, still wrong.
    return saveMono;
});
~~~

`defer` only defers **creating the inner subscription**; it does not attach the child to the outer chain. Correct:

~~~java
return Mono.defer(() -> saveMono.flatMap(
        saved -> auditMonoFor(saved).thenReturn(saved)));
~~~

### 12.3. `Mono.when(authorization, write)` Can Run the Write Early

~~~java
// WRONG: independent/may run in parallel.
return Mono.when(authorizationGuard, protectedWrite);
~~~

If the guard must run before the write, use `authorizationGuard.then(protectedWrite)` **with a guard that errors on deny**. `Mono.when` is for independent sources, not enforcing authorization ordering.

### 12.4. `onErrorResume(... -> Mono.empty())` Can Turn Errors into Success

~~~java
// WRONG when checking permissions:
return verifyPermission()
        .onErrorResume(e -> Mono.empty())
        .then(writeData());
~~~

If `verifyPermission()` emits `AccessDeniedException` and gets turned into empty completion, `then` runs `writeData()`. For mandatory permissions, propagating the error or mapping to an explicit deny publisher is mandatory. Likewise, `onErrorComplete()`/`onErrorReturn(true)` are dangerous on authz gates.

### 12.5. `concatMap` vs. `flatMap` for Ordered Side Effects

When processing an ordered `Flux<Command>` containing writes, `flatMap(this::process)` can interleave and execute concurrently; `concatMap(this::process)` preserves order. Design transactions, race protection, and idempotency separately. Even with `concatMap`, validate actor/tenant/action per command—ordering does not replace authorization.

### 12.6. `cache()`/`share()` and Multi-Subscriber Authorization

~~~java
// WRONG if authorization depends on actor/subscription:
Mono<Boolean> globallyCachedGrant = checkPermissionForCurrentUser()
        .cache();
~~~

`cache()` can store a decision from one subscription and replay it to another subscriber. If the current actor comes from Reactor Context, a later subscriber with a different context can still receive the stale decision. Never globally cache `Mono<AuthorizationDecision>` across unidentified users; re-evaluate sensitive decisions or key caches by tenant, actor, action, resource, and ACL/policy revisions with verified invalidation.

### 12.7. `create()`/`sink()` and Unclear Callback Lifecycles

When bridging callback APIs into Reactor via `Mono.create`/`Flux.create`, register cancellation/disposal hooks, ensure callbacks stop emitting after cancel, and never run security checks on a raw thread lacking context. For DBs or message brokers, verify concurrency, backpressure, event loss, shutdown, and errors. Prefer native reactive integrations with well-defined contracts whenever available.

### 12.8. `doOnNext` Is Not for Logging Secrets

Log redacted IDs, correlation IDs, outcomes, and verified tenants; never log JWTs, raw document bodies, or entire `SecurityContext` objects. A manual child subscription can drop MDC/trace context and leave audits without an actor. Reactor Context and logging MDC bridges require explicit configuration, testing, and cleanup.

## 13. Security and Lifecycle Test Matrix

| Test Case | Expected |
| --- | --- |
| Alice has READ on alpha, ID 7 | 200, alpha content |
| Bob has READ on beta, ID 7 | 200, beta content, isolated |
| Bob requests alpha | DENY before store/response |
| Viewer has tenant but lacks feature authority | DENY |
| Anonymous, missing Reactor Context | DENY |
| Service `rename` assembled without subscribing | Zero writes |
| Denied `rename` subscribed | Error, zero writes |
| Authorized `rename` subscribed | One write in matching tenant |
| Permission `Mono.empty()` | DENY, does not continue via `then` |
| Authorization `Mono.error()` | Zero writes, error metrics emitted |
| Ignored child `subscribe()` | Caught by lint/tests |
| Audit publisher fails | Outer publisher does not report success if audit is mandatory |
| HTTP cancellation before effect | Unsubscribed effect does not run |
| HTTP cancellation after commit | Reconciliation/idempotency handles it; no fake rollback |
| Retry after timeout | No duplicate non-idempotent side effects |
| Blocking driver on event loop | Detected by performance tests / BlockHound |
| Legacy blocking wrapper | `boundedElastic`, bounded timeout/concurrency |
| Same publisher under Alice then Bob | Per-subscriber permissions, no cached grant |
| Self-invocation into annotated method | Proxy bypass caught |
| `@Async` task on new thread | Does not reuse old tenant/security context |
| Outbox worker receives duplicate event | Idempotent, no duplicate charges/sends |
| Tenant membership revoked while job pending | Worker re-authorizes against current policy |
| Unauthorized resource with shared ID | Repository/cache strictly tenant-scoped |
| No request subscriber | Zero protected eager side effects |
| `Flux` with many items and one unauthorized item | Never emits protected data before authorization |
| Reactor context flows across `publishOn` | Not confused with `ThreadLocal` |
| Spring Security version upgrade | Re-test method annotation/adapter behavior |
| Dead-letter queues and logs | Contain no raw JWTs/secrets |
| Metrics/traces | Capture detached errors/cancellations without losing correlation |

### 13.1. Mutation Tests

Intentionally break critical safeguards on a test branch:
- Change `DocStore.rename` from `Mono.defer` to an eager update ⇒ "no subscription" test must fail.
- Remove `@PreAuthorize` and membership guards ⇒ viewer/Bob negative tests must fail.
- Replace `guard.then(store.rename)` with `Mono.when(guard, store.rename)` ⇒ zero-side-effect-on-DENY test must fail.
- Change `defaultIfEmpty(false)` to `defaultIfEmpty(true)` ⇒ missing-membership test must fail.
- Call `auditMono.subscribe()` instead of `flatMap` ⇒ audit-failure-propagated test must fail.
- Globally cache Alice's decision and reuse for Bob ⇒ context isolation test must fail.

If those mutations do not break tests, the test suite does not yet prove the security boundary.

## 14. Code Review Checklist for WebFlux Method Security

- [ ] Protected service methods reside on Spring-managed beans invoked via AOP proxies; no self-invocation into method security.
- [ ] WebFlux/MVC stack is cleanly chosen; reactive methods return supported `Mono`/`Flux`.
- [ ] Zero `block()` calls inside controllers, services, custom reactive managers, or the Reactor event loop.
- [ ] Necessary blocking I/O is deferred with `fromCallable` and boundedly offloaded, never disguised as non-blocking.
- [ ] Zero `subscribe()` calls inside `map`/`flatMap`/`doOnNext`/services to "force tasks to run".
- [ ] Authorization checks compose ahead of protected I/O; denied/unknown/error never complete as success.
- [ ] `Mono.defer`/reactive repositories keep side effects lazy until subscription.
- [ ] Principals come from verified Reactor Context; tenant arguments are treated strictly as selectors to verify.
- [ ] Method security advisors and `@PreAuthorize` are actually tested through Spring proxies.
- [ ] Mutations enforce transactions, versions, tenant predicates, and idempotency on retries.
- [ ] Errors, cancellations, and timeouts flow through the same chain; API response contracts are explicit.
- [ ] Mandatory business effects are never fire-and-forget and never report success before durability.
- [ ] Intentional background jobs use an outbox/queue with owner/lifecycle, auth, retries, DLQs, dedup, and observability.
- [ ] Raw JWTs or full `Authentication` objects are never stored/copied into queues/tasks for indefinite reuse.
- [ ] ALLOW decisions or personalized publishers are never cached across principals.
- [ ] Tests cover "not subscribed ⇒ not written", denied writes, two tenants with the same ID, and per-subscriber context.
- [ ] If using `doFinally`/`usingWhen`, cleanup and error propagation have explicit contracts.
- [ ] Logging and metrics are protected against PII/secret leaks and context loss.

## 15. Practice Exercises

**Question 1 — How do `block()` and `subscribe()` differ?**  
**Answer:** `block()` creates a subscription and waits synchronously on the calling thread; `subscribe()` triggers a subscription and usually returns immediately, especially for async sources. Both can spawn subscriptions outside WebFlux's managed chain if invoked inside services, breaking boundaries in different ways.

**Question 2 — Is `Mono.just(jdbcDao.save(...))` non-blocking?**  
**Answer:** No; `jdbcDao.save(...)` executes immediately during assembly. Use a reactive driver or `Mono.fromCallable(...).subscribeOn(boundedElastic)` if blocking I/O must be isolated temporarily.

**Question 3 — Is `canWrite(tenant).then(save(...))` safe?**  
**Answer:** No, if `canWrite` returns a `Mono<Boolean>` completing with `false` or empty; `then` ignores the emitted value and runs the write. Map `false`/empty to `Mono.error(AccessDeniedException)` before `then`.

**Question 4 — Why is `audit(record).subscribe()` inside `doOnNext` dangerous?**  
**Answer:** It creates a detached child subscription; HTTP can return success before auditing finishes, and errors, cancellation, tracing, and security context are no longer managed with the request. For mandatory audits, use `flatMap(saved -> audit(saved).thenReturn(saved))`.

**Question 5 — Is manual `subscribe()` ever appropriate?**  
**Answer:** Yes, at lifecycle-owning boundaries such as managed scheduled workers or queue consumers that establish their own authentication/tenant context, track `Disposable`, and handle retries, backpressure, and shutdown—never inside library/service methods returning a `Publisher` to callers.

**Question 6 — Why doesn't cancellation always undo DB mutations?**  
**Answer:** Cancellation is a subscription signal; an external DB commit may already have completed. Transactions, idempotency, and reconciliation ensure consistency rather than treating cancel as undo.

**Question 7 — Is it safe for Alice and Bob to subscribe to the same cached decision `Mono`?**  
**Answer:** No, if the `Mono` caches Alice's permission outcome and replays it to Bob. Never globally cache ALLOW per subscriber; evaluate against source policy or use properly scoped cache keys and freshness guarantees.

**Question 8 — Should a worker running one hour after a user's membership was revoked rely on a cached ALLOW?**  
**Answer:** Not by default. Workers should re-verify task/tenant/actor permissions or run under a delegated service policy with explicit expiry and authority bounds. An outbox guarantees durable intent, not that the user still holds permission at processing time.

## 16. Conclusion

In reactive method security, **authorization must be a link in the same processing chain as data access and side effects**, never a check "fired off" with `subscribe()` or waited on with `block()` on the event loop.

~~~text
WebFlux subscriber + Reactor SecurityContext
  -> @PreAuthorize / ReactiveAuthorizationManager
  -> verified tenant + actor + action
  -> lazy/nonblocking protected operation
  -> mandatory persistence/audit/outbox
  -> onNext/onComplete OR onError/cancel under explicit contract
  -> HTTP response / durable job handoff
~~~

Use `flatMap`/`then` to keep mandatory obligations in the chain, `Mono.defer` to avoid eager effects, bounded `fromCallable` + `boundedElastic` for unavoidable blocking libraries, and **outbox + managed workers** when background work is genuinely needed post-request. Never use `subscribe()` as a "run task" button inside business services. Final review question: **"If the request is denied, never subscribed to, times out, or the client disconnects, can a write, privilege grant, mandatory event, or sensitive download still run outside the PEP's control?"** If yes, bring that work into the chain or establish an independent background authorization boundary.

## Official References

- [Spring Security – Reactive Method Security 6.5](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html): Reactor Context, `@EnableReactiveMethodSecurity`, `@PreAuthorize`, and reactive authorization advisors.
- [Spring Security – ReactiveSecurityContextHolder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html): reading/writing `Authentication` in Reactor subscriber Context.
- [Spring Security – WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): reactive `SecurityWebFilterChain`, request authentication.
- [Spring Framework 6.2 – WebFlux Concurrency Model](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/new-framework.html): event loop, non-blocking model, and blocking API considerations.
- [Project Reactor – Introduction to Reactive Programming](https://projectreactor.io/docs/core/release/reference/reactiveProgramming.html): cold `Publisher`s, subscriptions, signals, and backpressure.
- [Project Reactor – FAQ: Wrap synchronous blocking call](https://projectreactor.io/docs/core/release/reference/faq.html): `fromCallable` + `subscribeOn(boundedElastic)`.
- [Project Reactor – Adding a Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): `contextWrite`, `deferContextual`, subscriber context propagation.
- [Project Reactor – Backpressure and subscribing](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html): `subscribe()`, request demand, bounded backpressure.
- [Project Reactor – Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, virtual time, `TestPublisher`, and cancellation tests.
- [Spring Framework – Reactive Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html#tx-prog-operator): transactional reactive operators and lifecycle.
