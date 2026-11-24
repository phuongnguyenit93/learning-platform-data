# Calling Asynchronous Authorization Services in Reactive Decisions

## 1. Problem and Objectives

In a Spring WebFlux application, an authorization decision is not always as simple as `hasRole("USER")`. For example, when reading `Document#42`, the application may need to query an internal **authorization service (PDP / permission service)** over the network, query an ACL via R2DBC, or evaluate policies based on tenant, owner, and record status. The result arrives **only after asynchronous I/O**.

With **Reactive Method Security**, you should never call `block()` to wait for the result. Spring Security 6.5, in `AuthorizationManager` mode, allows a bean invoked inside `@PreAuthorize` to return `Mono<Boolean>`. The framework integrates that decision publisher into the reactive authorization pipeline, denies execution when the result is `false`, and proceeds to business logic only when the decision permits it.

Objectives for this lesson, part of the **Reactive Method Security** topic in Spring Security Authorization:

1. Know when to use `@EnableReactiveMethodSecurity`, `@PreAuthorize`, and a custom bean returning `Mono<Boolean>`.
2. Read authentication from `ReactiveSecurityContextHolder` (Reactor Context) instead of relying on traditional `ThreadLocal`.
3. Compose asynchronous permission calls with `flatMap`, without accidentally creating `Mono<Mono<Boolean>>`.
4. Clearly define `true`, `false`, `Mono.empty()`, remote errors, timeouts, and fail-closed behavior.
5. Never block the Netty event loop with `block()`, and never call `.subscribe()` manually to run decisions out-of-band.
6. Validate actor, authority, tenant, resource type/ID, owner, and status when calling a PDP.
7. Protect the data layer too: preauthorization does not replace transactions, tenant filters, or write-time rechecks.
8. Test using Java 17+, JUnit 5, a real Spring context, and `StepVerifier`: allow/deny, grant/revoke, errors/timeouts, two tenants sharing an ID, and two users sharing a username.

**Scope:** The runnable project in section 7 simulates the PDP using `Mono.delay` and data in a `ConcurrentHashMap`; it **does not** test HTTP networking, `WebClient`, R2DBC, or PostgreSQL directly. Snippets using `WebClient`/R2DBC in the production section are explicitly marked as fragments.

## 2. Where Does Reactive Method Authorization Fit?

```text
Caller -> Spring-managed bean proxy
   |
   | service.read("TENANT_A", 42) : Mono<String>
   v
@EnableReactiveMethodSecurity / @PreAuthorize
   |
   | SpEL: @authz.canRead(#tenant, #id)
   v
AsyncPolicy.canRead(...)
   |
   +-- ReactiveSecurityContextHolder.getContext()
   |      -> Authentication -> stable subject + tenant + authorities
   |      -> wrong principal/tenant/action => DENY
   |
   +-- RemotePermissionService.check(...) : Mono<Boolean>
          |
          +-- true  -> subscribe to business publisher
          +-- false -> access denied; no data processed
          +-- empty -> explicit DENY
          +-- error/timeout -> explicit DENY or safe error contract
```

In WebFlux, the Reactor Context holds the `SecurityContext` for the subscribed publisher. I/O steps can hop across threads, so calling `SecurityContextHolder.getContext()` on `ThreadLocal` may retrieve the wrong context or no authentication at all.

| Mechanism | Extension Point | Protected Target |
| --- | --- | --- |
| Reactive **method** security | `@EnableReactiveMethodSecurity`, `@PreAuthorize` | Spring-managed service methods returning `Mono`/`Flux` |
| WebFlux **HTTP** authorization | `ServerHttpSecurity.authorizeExchange` and `ReactiveAuthorizationManager<AuthorizationContext>` | `ServerWebExchange`, HTTP path/method |
| Servlet method security | `@EnableMethodSecurity`, `AuthorizationManager<MethodInvocation>` | Imperative method invocations |

**Do not mix them up:** annotations look similar, yet reactive method security requires reactive interceptors, Reactor Context, and `Publisher`s. An HTTP filter can block external requests, but it does not protect jobs or message consumers calling services directly.

## 3. Calling an Authorization Bean Returning `Mono<Boolean>`

Spring Security 6.5 supports:

```java
@PreAuthorize("@authz.canRead(#tenant, #id)")
public Mono<String> read(
        @P("tenant") String tenant,
        @P("id") long id) {
    return repository.read(tenant, id);
}
```

- A Spring bean named **`authz`** exposes a public method `canRead(String, long)` returning `Mono<Boolean>`.
- `@P` is `org.springframework.security.access.method.P`: SpEL can resolve `#tenant` and `#id` even if the compiler does not enable `-parameters`.
- The service is declared via `@Bean` or `@Component` and invoked **through a proxy**.
- When `false` is returned, Spring Security emits an authorization error (typically `AccessDeniedException`/a subclass).
- Keep side effects inside a lazy publisher (`Mono.defer`, reactive repository) and enforce domain checks at write time.
- `@EnableReactiveMethodSecurity` in Spring Security 6.x defaults to `AuthorizationManager`; legacy documentation limited to synchronous booleans must not be blindly applied to the new engine.

Illustrative policy bean:

```java
public Mono<Boolean> canRead(String tenant, long id) {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .flatMap(auth -> {
            // Validate auth, authority, and tenant before remote call.
            return remotePermissions.check(auth, tenant, id, "READ");
        })
        .defaultIfEmpty(false)
        .timeout(Duration.ofMillis(300))
        .onErrorReturn(false);
}
```

This is a **fragment**: `remotePermissions` and validation conditions must be implemented. The complete Java example in section 7 provides full validation and fail-closed handling.

### 3.1. Why `flatMap` Instead of `map`?

```java
// WRONG type: Mono<Mono<Boolean>>.
Mono<Mono<Boolean>> nested =
    actorPublisher.map(actor -> remote.check(actor));

// RIGHT: Mono<Boolean>, Spring Security can evaluate it.
Mono<Boolean> decision =
    actorPublisher.flatMap(actor -> remote.check(actor));
```

`actorPublisher` and `remote` merely illustrate operators. A `Mono<Boolean>` is not an already-computed boolean; never do:

```java
// COUNTEREXAMPLE: blocking in reactive authorization path.
boolean allow = remote.check(actor).block();

// COUNTEREXAMPLE: manual subscribe, then returning ALLOW early.
remote.check(actor).subscribe(result -> audit(result));
return Mono.just(true);
```

**Right:** return the entire publisher so the framework manages subscription, errors, and Reactor Context.

### 3.2. `empty`, Errors, and Timeouts

| Signal from PDP | Safe Interpretation in Example |
| --- | --- |
| `Mono.just(true)` | PDP allows, after verifying scope/action |
| `Mono.just(false)` | PDP denies |
| `Mono.empty()` | No rule or resource found; **explicit DENY** via `defaultIfEmpty(false)` |
| `Mono.error(...)` | PDP failure; **fail closed**, never auto-allow |
| `Mono.never()` | PDP hangs; apply `timeout` and fail closed |
| Cancellation | Do not keep running via detached `subscribe()`; upstream handles cancellation reactively |

Spring Security docs explain that `Mono.empty()` from a custom authorization bean may be treated as **abstain**. To avoid accidentally turning "unknown" into ALLOW, this project explicitly converts empty results from the **remote service** into `false` before returning to method authorization. If writing a custom `ReactiveAuthorizationManager` or combining multiple managers, define abstain semantics explicitly.

`timeout(Duration.ofMillis(100)).onErrorReturn(false)` is for **demo** purposes. Production may translate PDP outages into 503 and alerts instead of 403; the invariant is **never fail open**. Avoid caching ALLOWs for too long, or revoked permissions will remain active via stale entries.

## 4. Decision Design: Beyond Just `username` and `documentId`

A sufficiently secure policy usually includes:

```text
actor    = tenant + issuer + stable subject
action   = READ | WRITE | DELETE | APPROVE | EXPORT
resource = tenant + resource type + ID
context  = status + owner + sensitivity level + policy revision
```

Example:

| Tenant | ID | Username | Issuer/subject owner | Status | Body |
| --- | ---: | --- | --- | --- | --- |
| TENANT_A | 42 | alex | `issuer-1/sub-a` | DRAFT | A draft 42 |
| TENANT_B | 42 | alex | `issuer-1/sub-b` | DRAFT | B draft 42 |
| TENANT_A | 43 | publisher | `issuer-1/editor` | PUBLISHED | A public 43 |

Both accounts are named **alex** and both document IDs are **42**, yet their tenants and subjects differ. If the PDP receives only `username="alex", documentId=42`, permissions can leak across tenants.

**Example policy:**

- `READ`: requires `DOC_READ` authority, matching tenant, remote READ grant; `DRAFT` only for the owner matching issuer+subject, `PUBLISHED` readable with a grant.
- `WRITE`: requires `DOC_WRITE`, matching tenant, remote WRITE grant, matching owner, and `DRAFT` state.
- A caller passing another tenant in a method parameter **does not alter membership** and must be rejected before calling the remote PDP.
- Missing grants, missing documents, or PDP outages all result in DENY.
- Same subject with a different issuer, or same username with a different subject, must never inherit permissions.

**Trust boundary:** identity should come from a JWT/OIDC token with verified signature, issuer, audience, lifetime, and tenant membership. Java test data constructing a principal **only simulates completed authentication**; never turn client-supplied `X-User`, `X-Tenant`, or `subject` strings into a trusted `Authentication`.

## 5. Calling Permission Services via WebClient and R2DBC

### 5.1. WebClient

Example request/response to an internal PDP:

```json
{
  "actor": {
    "tenant": "TENANT_A",
    "issuer": "https://idp.example.test",
    "subject": "sub-a"
  },
  "action": "READ",
  "resource": {
    "tenant": "TENANT_A",
    "type": "Document",
    "id": 42
  }
}
```

```json
{"allowed":true,"policyVersion":17}
```

An implementation fragment (not standalone, as it requires `webClient`, DTOs, and beans):

```java
public Mono<Boolean> check(DecisionRequest request) {
    return webClient.post()
        .uri("/internal/decisions")
        .bodyValue(request)
        .retrieve()
        .bodyToMono(DecisionResponse.class)
        .map(DecisionResponse::allowed)
        .defaultIfEmpty(false)
        .timeout(Duration.ofMillis(300));
}
```

The caller layer should provide `onErrorReturn(false)` or an error contract, metrics, and token-free logs. Never let users pick the PDP URL or supply `allowed` in the request. Use service-to-service authentication, TLS/mTLS, network ACLs, and schema validation. On 4xx/5xx, `WebClient` emits a Publisher error; **never interpret HTTP 200 with an empty body as ALLOW**.

### 5.2. R2DBC

A reactive SQL fragment:

```java
return databaseClient.sql("""
    SELECT allowed
    FROM permission_rules
    WHERE tenant_id = :tenant
      AND actor_issuer = :issuer
      AND actor_subject = :subject
      AND action = :action
      AND resource_id = :id
""")
    .bind("tenant", actor.tenant())
    .bind("issuer", actor.issuer())
    .bind("subject", actor.subject())
    .bind("action", action)
    .bind("id", id)
    .map((row, meta) -> row.get("allowed", Boolean.class))
    .one()
    .defaultIfEmpty(false);
```

This is only a grant lookup and is **insufficient without object owner/status, tenant RLS, and workflow checks**. R2DBC/reactive clients suit the event loop. `Mono.just(jdbcTemplate.queryForObject(...))` is a **blocking counterexample** and does not make JDBC asynchronous.

### 5.3. Failures and Load Control

- **Timeouts:** enforce dedicated timeouts for the PDP and overall requests; never wait indefinitely.
- **Retries:** apply intentionally only to idempotent decision lookups with backoff/jitter and a retry cap; never retry a valid DENY.
- **Circuit breakers:** on PDP outages, never fall back to `true`; distinguish system errors from denials in audits and metrics.
- **Concurrency:** when checking permissions per item in a `Flux`, avoid unbounded `flatMap`; batching or filtering directly inside the data query is usually far more efficient.
- **Caching:** keys must include tenant, actor issuer/sub, action, resource type/ID, and policy revision; invalidate upon grant/revoke.
- **Observability:** track latency, timeouts, errors, denials, and policy versions; never log raw JWTs, PII, or detailed ACLs in responses.

## 6. Reactive SecurityContext, AOP, and Side Effects

### 6.1. Context Per Subscriber

In tests or code without WebFlux HTTP filters:

```java
Mono<String> result = securedService.read("TENANT_A", 42L)
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(auth));
```

Here `auth` is the test-created `Authentication`. `contextWrite` binds the context **to the subscription**; when running `StepVerifier.create(result)`, Spring method security and the policy bean see that principal.

Never use `SecurityContextHolder.getContext().getAuthentication()` as your primary source in Reactor, because reactive pipelines can switch threads. Never construct a shared `Mono` and `.cache()` authority decisions across actors without separating keys/context, or you risk leaking ALLOW decisions.

### 6.2. Proxies and Lazy Business Publishers

```java
@PreAuthorize("@authz.canWrite(#tenant,#id)")
public Mono<String> write(String tenant, long id, String body) {
    return Mono.defer(() -> {
        // Subscribed only after preauthorization allows.
        return repository.write(tenant, id, body);
    });
}
```

This fragment assumes a reactive repository. `@PreAuthorize` only runs on Spring-managed methods invoked through an AOP proxy; internal `this.write(...)` calls on the same target can bypass the interceptor.

Putting side effects before creating the `Mono` is wrong:

```java
public Mono<String> unsafeWrite(...) {
    jdbcTemplate.update(...); // Synchronous before subscription.
    return Mono.just("done");
}
```

This is a **counterexample** only, not a complete Java class. For high-risk operations, even proper preauthorization does not replace **rechecking owner/state/version inside the write transaction**, because permissions or state can change after the PDP returns allow (TOCTOU).

### 6.3. Reactive `Flux`

`@PreAuthorize` can guard calls to a service returning `Flux<T>`, yet the initial decision **does not guarantee every item** in the `Flux` is permitted. For lists and exports, query by tenant and object-level permissions while minimizing PDP RPCs. `@PostFilter` is not a replacement for pagination or row-level query security on large datasets.

## 7. Self-Contained Java 17+ and JUnit 5 Project

This sample uses **real `@EnableReactiveMethodSecurity`**, a SpEL `@authz` bean returning `Mono<Boolean>`, asynchronous `RemotePermissions`, and `StepVerifier`; it launches no HTTP server, requires no database, and uses no Testcontainers. It tests tenant separation with identical IDs/usernames, async permission evaluations, grant/revoke, timeouts, exceptions, and `Mono.empty()` sources.

### 7.1. Structure

```text
reactive-async-authz/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/AsyncReactiveAuthorizationTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'reactive-async-authz'
```

`build.gradle`:

```groovy
plugins { id 'java' }

repositories { mavenCentral() }

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.0'
    )
    testImplementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-core'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

**Single Java file:** `src/test/java/demo/AsyncReactiveAuthorizationTest.java`.

```java
package demo;

import java.security.Principal;
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

@SpringJUnitConfig(AsyncReactiveAuthorizationTest.Config.class)
public class AsyncReactiveAuthorizationTest {

    private static final String ISSUER = "https://idp.example.test";

    public record Actor(
        String tenant, String issuer, String subject, String username
    ) implements Principal {
        @Override public String getName() { return username; }
    }

    public record Resource(String tenant, long id) {}

    public record Doc(
        String tenant, long id, String ownerIssuer,
        String ownerSub, String status, String body
    ) {}

    public record Grant(
        Resource resource, String issuer, String subject,
        String action
    ) {}

    static final Actor ALICE =
        new Actor("TENANT_A", ISSUER, "sub-a", "alex");

    static final Actor BOB =
        new Actor("TENANT_B", ISSUER, "sub-b", "alex");

    static final Actor OTHER =
        new Actor("TENANT_A", ISSUER, "sub-other", "alex");

    static final Actor OTHER_ISSUER =
        new Actor("TENANT_A", "https://idp-other.test",
                  "sub-a", "alex");

    public static class Docs {
        private final Map<Resource, Doc> rows =
            new ConcurrentHashMap<>();

        void reset() {
            rows.clear();
            rows.put(new Resource("TENANT_A", 42L),
                new Doc("TENANT_A", 42L, ISSUER, "sub-a",
                    "DRAFT", "A private 42"));
            rows.put(new Resource("TENANT_B", 42L),
                new Doc("TENANT_B", 42L, ISSUER, "sub-b",
                    "DRAFT", "B private 42"));
            rows.put(new Resource("TENANT_A", 43L),
                new Doc("TENANT_A", 43L, ISSUER, "publisher",
                    "PUBLISHED", "A public 43"));
        }

        Doc find(String tenant, long id) {
            return rows.get(new Resource(tenant, id));
        }

        Mono<String> read(String tenant, long id) {
            return Mono.defer(() -> {
                Doc found = find(tenant, id);
                return found == null
                    ? Mono.error(new AccessDeniedException(
                        "Not visible"))
                    : Mono.just(found.body());
            });
        }

        Mono<String> write(
                String tenant, long id, Actor actor, String body) {
            return Mono.defer(() -> {
                AtomicBoolean changed = new AtomicBoolean();
                rows.computeIfPresent(
                    new Resource(tenant, id), (key, old) -> {
                        boolean owner =
                            actor.tenant().equals(old.tenant())
                            && actor.issuer().equals(old.ownerIssuer())
                            && actor.subject().equals(old.ownerSub());
                        if (!owner || !"DRAFT".equals(old.status())) {
                            return old;
                        }
                        changed.set(true);
                        return new Doc(
                            old.tenant(), old.id(), old.ownerIssuer(),
                            old.ownerSub(), old.status(), body);
                    });

                return changed.get()
                    ? Mono.just(body)
                    : Mono.error(new AccessDeniedException(
                        "Not owner or no longer draft"));
            });
        }

        void publish(String tenant, long id) {
            rows.computeIfPresent(
                new Resource(tenant, id),
                (key, old) -> new Doc(
                    old.tenant(), old.id(), old.ownerIssuer(),
                    old.ownerSub(), "PUBLISHED", old.body()));
        }
    }

    public static class RemotePermissions {
        private final Docs docs;
        private final Map<Grant, Boolean> grants =
            new ConcurrentHashMap<>();
        private final AtomicInteger calls = new AtomicInteger();
        private final AtomicBoolean available =
            new AtomicBoolean(true);
        private final AtomicBoolean hang =
            new AtomicBoolean(false);

        RemotePermissions(Docs docs) { this.docs = docs; }

        void reset() {
            grants.clear();
            calls.set(0);
            available.set(true);
            hang.set(false);
            grant("TENANT_A", 42L, ALICE, "READ");
            grant("TENANT_A", 42L, ALICE, "WRITE");
            grant("TENANT_B", 42L, BOB, "READ");
            grant("TENANT_B", 42L, BOB, "WRITE");
            grant("TENANT_A", 43L, ALICE, "READ");
        }

        private Grant key(
                String tenant, long id, Actor actor, String action) {
            return new Grant(
                new Resource(tenant, id),
                actor.issuer(), actor.subject(), action);
        }

        void grant(String tenant, long id, Actor actor, String action) {
            grants.put(key(tenant, id, actor, action), true);
        }

        void revoke(String tenant, long id, Actor actor, String action) {
            grants.remove(key(tenant, id, actor, action));
        }

        int calls() { return calls.get(); }
        void outage(boolean state) { available.set(!state); }
        void stall(boolean state) { hang.set(state); }

        Mono<Boolean> check(
                Actor actor, String tenant, long id, String action) {
            return Mono.defer(() -> {
                calls.incrementAndGet();

                if (hang.get()) {
                    return Mono.<Boolean>never();
                }

                // Delay runs on Reactor scheduler: asynchronous PDP.
                return Mono.delay(Duration.ofMillis(5))
                    .flatMap(ignored -> {
                        if (!available.get()) {
                            return Mono.<Boolean>error(
                                new IllegalStateException(
                                    "Remote PDP unavailable"));
                        }
                        Doc doc = docs.find(tenant, id);
                        if (doc == null) {
                            // No rule/resource found:
                            // policy wrapper must turn empty -> deny.
                            return Mono.<Boolean>empty();
                        }

                        boolean owner =
                            actor.tenant().equals(doc.tenant())
                            && actor.issuer().equals(doc.ownerIssuer())
                            && actor.subject().equals(doc.ownerSub());

                        boolean scopeAllowed =
                            "READ".equals(action)
                                ? "PUBLISHED".equals(doc.status()) || owner
                                : "WRITE".equals(action)
                                    && owner
                                    && "DRAFT".equals(doc.status());

                        boolean granted = Boolean.TRUE.equals(
                            grants.get(key(tenant, id, actor, action)));

                        return Mono.just(granted && scopeAllowed);
                    });
            });
        }
    }

    public static class AsyncPolicy {
        private final RemotePermissions remote;

        AsyncPolicy(RemotePermissions remote) { this.remote = remote; }

        public Mono<Boolean> canRead(String tenant, long id) {
            return can(tenant, id, "READ");
        }

        public Mono<Boolean> canWrite(String tenant, long id) {
            return can(tenant, id, "WRITE");
        }

        private Mono<Boolean> can(
                String tenant, long id, String action) {
            return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .flatMap(auth -> {
                    if (auth == null || !auth.isAuthenticated()
                        || !(auth.getPrincipal() instanceof Actor actor)
                        || tenant == null || tenant.isBlank()
                        || !tenant.equals(actor.tenant())
                        || actor.issuer() == null
                        || actor.issuer().isBlank()
                        || actor.subject() == null
                        || actor.subject().isBlank()
                        || id <= 0) {
                        return Mono.just(false);
                    }

                    String needed = "DOC_" + action;
                    boolean hasAuthority =
                        auth.getAuthorities().stream()
                            .anyMatch(a ->
                                needed.equals(a.getAuthority()));

                    if (!hasAuthority) {
                        return Mono.just(false);
                    }

                    return remote.check(actor, tenant, id, action)
                        .timeout(Duration.ofMillis(100))
                        .defaultIfEmpty(false)
                        .onErrorReturn(false);
                })
                .defaultIfEmpty(false);
        }
    }

    public static class Probe {
        private final AtomicInteger reads = new AtomicInteger();
        private final AtomicInteger writes = new AtomicInteger();

        void read() { reads.incrementAndGet(); }
        void write() { writes.incrementAndGet(); }
        int reads() { return reads.get(); }
        int writes() { return writes.get(); }
        void reset() { reads.set(0); writes.set(0); }
    }

    public static class DocumentService {
        private final Docs docs;
        private final Probe probe;

        DocumentService(Docs docs, Probe probe) {
            this.docs = docs;
            this.probe = probe;
        }

        @PreAuthorize("@authz.canRead(#tenant, #id)")
        public Mono<String> read(
                @P("tenant") String tenant,
                @P("id") long id) {
            return Mono.defer(() -> {
                probe.read();
                return docs.read(tenant, id);
            });
        }

        @PreAuthorize("@authz.canWrite(#tenant, #id)")
        public Mono<String> write(
                @P("tenant") String tenant,
                @P("id") long id, String body) {
            return Mono.defer(() -> {
                probe.write();
                return ReactiveSecurityContextHolder.getContext()
                    .map(SecurityContext::getAuthentication)
                    .map(auth -> (Actor) auth.getPrincipal())
                    .flatMap(actor ->
                        docs.write(tenant, id, actor, body));
            });
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableReactiveMethodSecurity
    public static class Config {
        @Bean Docs docs() {
            return new Docs();
        }

        @Bean RemotePermissions remotePermissions(Docs docs) {
            return new RemotePermissions(docs);
        }

        @Bean("authz")
        AsyncPolicy asyncPolicy(RemotePermissions remote) {
            return new AsyncPolicy(remote);
        }

        @Bean Probe probe() {
            return new Probe();
        }

        @Bean DocumentService documentService(
                Docs docs, Probe probe) {
            return new DocumentService(docs, probe);
        }
    }

    @Autowired Docs docs;
    @Autowired RemotePermissions remote;
    @Autowired DocumentService service;
    @Autowired Probe probe;

    private static <T> Mono<T> as(
            Actor actor, Mono<T> source, String... authorities) {
        Authentication auth =
            new UsernamePasswordAuthenticationToken(
                actor, "test-only",
                AuthorityUtils.createAuthorityList(authorities));

        return source.contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(auth));
    }

    private static <T> Mono<T> asString(
            String name, Mono<T> source, String... authorities) {
        Authentication auth =
            new UsernamePasswordAuthenticationToken(
                name, "test-only",
                AuthorityUtils.createAuthorityList(authorities));

        return source.contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(auth));
    }

    @BeforeEach
    void reset() {
        docs.reset();
        remote.reset();
        probe.reset();
    }

    @Test
    void springAopReallyProtectsTheService() {
        assertThat(AopUtils.isAopProxy(service)).isTrue();
    }

    @Test
    void aliceReadsA42AfterAsyncPermission() {
        StepVerifier.create(as(
            ALICE, service.read("TENANT_A", 42L), "DOC_READ"))
            .expectNext("A private 42")
            .verifyComplete();

        assertThat(remote.calls()).isEqualTo(1);
        assertThat(probe.reads()).isEqualTo(1);
    }

    @Test
    void bobReadsB42WithTheSameLocalId() {
        StepVerifier.create(as(
            BOB, service.read("TENANT_B", 42L), "DOC_READ"))
            .expectNext("B private 42")
            .verifyComplete();

        assertThat(docs.find("TENANT_A", 42L).body())
            .isEqualTo("A private 42");
    }

    @Test
    void twoActorsHaveSameUsernameButDifferentIdentity() {
        assertThat(ALICE.getName()).isEqualTo(BOB.getName());
        assertThat(ALICE.subject()).isNotEqualTo(BOB.subject());
    }

    @Test
    void aliceCannotUseTenantBAsMethodArgument() {
        StepVerifier.create(as(
            ALICE, service.read("TENANT_B", 42L), "DOC_READ"))
            .expectError(AccessDeniedException.class)
            .verify();

        assertThat(remote.calls()).isZero();
        assertThat(probe.reads()).isZero();
    }

    @Test
    void bobCannotUseTenantAAsMethodArgument() {
        StepVerifier.create(as(
            BOB, service.read("TENANT_A", 42L), "DOC_READ"))
            .expectError(AccessDeniedException.class)
            .verify();
        assertThat(remote.calls()).isZero();
    }

    @Test
    void wrongAuthorityDeniesBeforeRemoteCall() {
        StepVerifier.create(as(
            ALICE, service.read("TENANT_A", 42L), "DOC_WRITE"))
            .expectError(AccessDeniedException.class)
            .verify();

        assertThat(remote.calls()).isZero();
        assertThat(probe.reads()).isZero();
    }

    @Test
    void sameNameDifferentSubjectCannotUseDraftEvenIfGranted() {
        remote.grant("TENANT_A", 42L, OTHER, "READ");

        StepVerifier.create(as(
            OTHER, service.read("TENANT_A", 42L), "DOC_READ"))
            .expectError(AccessDeniedException.class)
            .verify();

        assertThat(probe.reads()).isZero();
    }

    @Test
    void sameSubjectDifferentIssuerCannotImpersonateOwner() {
        remote.grant("TENANT_A", 42L, OTHER_ISSUER, "READ");

        StepVerifier.create(as(
            OTHER_ISSUER,
            service.read("TENANT_A", 42L), "DOC_READ"))
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    void withoutRemoteGrantPublishedDocumentIsStillDenied() {
        StepVerifier.create(as(
            OTHER, service.read("TENANT_A", 43L), "DOC_READ"))
            .expectError(AccessDeniedException.class)
            .verify();
        assertThat(remote.calls()).isEqualTo(1);
    }

    @Test
    void grantIsObservedOnNextAsyncDecision() {
        StepVerifier.create(as(
            OTHER, service.read("TENANT_A", 43L), "DOC_READ"))
            .expectError(AccessDeniedException.class)
            .verify();

        remote.grant("TENANT_A", 43L, OTHER, "READ");

        StepVerifier.create(as(
            OTHER, service.read("TENANT_A", 43L), "DOC_READ"))
            .expectNext("A public 43")
            .verifyComplete();

        assertThat(remote.calls()).isEqualTo(2);
    }

    @Test
    void revokeIsObservedWithoutCachingOldAllow() {
        StepVerifier.create(as(
            ALICE, service.read("TENANT_A", 42L), "DOC_READ"))
            .expectNext("A private 42")
            .verifyComplete();

        remote.revoke("TENANT_A", 42L, ALICE, "READ");

        StepVerifier.create(as(
            ALICE, service.read("TENANT_A", 42L), "DOC_READ"))
            .expectError(AccessDeniedException.class)
            .verify();

        assertThat(remote.calls()).isEqualTo(2);
        assertThat(probe.reads()).isEqualTo(1);
    }

    @Test
    void emptyRemoteResultForMissingDocumentFailsClosed() {
        StepVerifier.create(as(
            ALICE, service.read("TENANT_A", 999L), "DOC_READ"))
            .expectError(AccessDeniedException.class)
            .verify();
        assertThat(probe.reads()).isZero();
    }

    @Test
    void remoteOutageFailsClosed() {
        remote.outage(true);

        StepVerifier.create(as(
            ALICE, service.read("TENANT_A", 42L), "DOC_READ"))
            .expectError(AccessDeniedException.class)
            .verify();

        assertThat(remote.calls()).isEqualTo(1);
        assertThat(probe.reads()).isZero();
    }

    @Test
    void remoteTimeoutFailsClosed() {
        remote.stall(true);

        StepVerifier.create(as(
            ALICE, service.read("TENANT_A", 42L), "DOC_READ"))
            .expectError(AccessDeniedException.class)
            .verify();

        assertThat(remote.calls()).isEqualTo(1);
        assertThat(probe.reads()).isZero();
    }

    @Test
    void plainUsernamePrincipalCannotBorrowAuthorization() {
        StepVerifier.create(asString(
            "alex", service.read("TENANT_A", 42L), "DOC_READ"))
            .expectError(AccessDeniedException.class)
            .verify();

        assertThat(remote.calls()).isZero();
    }

    @Test
    void workStartsOnlyAfterSubscription() {
        Mono<String> pipeline = as(
            ALICE, service.read("TENANT_A", 42L), "DOC_READ");

        assertThat(remote.calls()).isZero();
        assertThat(probe.reads()).isZero();

        StepVerifier.create(pipeline)
            .expectNext("A private 42")
            .verifyComplete();

        assertThat(remote.calls()).isEqualTo(1);
    }

    @Test
    void secondSubscriptionReevaluatesRevokedPolicy() {
        Mono<String> secured = as(
            ALICE, service.read("TENANT_A", 42L), "DOC_READ");

        StepVerifier.create(secured)
            .expectNext("A private 42")
            .verifyComplete();

        remote.revoke("TENANT_A", 42L, ALICE, "READ");

        StepVerifier.create(secured)
            .expectError(AccessDeniedException.class)
            .verify();

        assertThat(remote.calls()).isEqualTo(2);
    }

    @Test
    void aliceWritesOnlyTenantADraft() {
        StepVerifier.create(as(
            ALICE,
            service.write("TENANT_A", 42L, "Modified A"),
            "DOC_WRITE"))
            .expectNext("Modified A")
            .verifyComplete();

        assertThat(docs.find("TENANT_A", 42L).body())
            .isEqualTo("Modified A");
        assertThat(docs.find("TENANT_B", 42L).body())
            .isEqualTo("B private 42");
        assertThat(probe.writes()).isEqualTo(1);
    }

    @Test
    void bobWritesOnlyTenantBDraft() {
        StepVerifier.create(as(
            BOB,
            service.write("TENANT_B", 42L, "Modified B"),
            "DOC_WRITE"))
            .expectNext("Modified B")
            .verifyComplete();

        assertThat(docs.find("TENANT_A", 42L).body())
            .isEqualTo("A private 42");
        assertThat(docs.find("TENANT_B", 42L).body())
            .isEqualTo("Modified B");
    }

    @Test
    void readPermissionDoesNotGrantWriteMethod() {
        StepVerifier.create(as(
            ALICE,
            service.write("TENANT_A", 42L, "Forbidden"),
            "DOC_READ"))
            .expectError(AccessDeniedException.class)
            .verify();

        assertThat(remote.calls()).isZero();
        assertThat(probe.writes()).isZero();
    }

    @Test
    void publishedDocumentCannotBeChangedEvenByFormerOwner() {
        docs.publish("TENANT_A", 42L);

        StepVerifier.create(as(
            ALICE,
            service.write("TENANT_A", 42L, "Forbidden"),
            "DOC_WRITE"))
            .expectError(AccessDeniedException.class)
            .verify();

        assertThat(docs.find("TENANT_A", 42L).body())
            .isEqualTo("A private 42");
        assertThat(probe.writes()).isZero();
    }
}
```

### 7.2. Running and Interpreting Results

In the project directory:

```bash
gradle test --tests demo.AsyncReactiveAuthorizationTest
```

With the Gradle Wrapper, run `./gradlew test --tests demo.AsyncReactiveAuthorizationTest` (Linux/macOS) or `gradlew.bat test --tests demo.AsyncReactiveAuthorizationTest` (Windows).

**Expected:** all 22 JUnit tests pass and Gradle reports `BUILD SUCCESSFUL` in a compatible environment. This is the **expected outcome from the code**, not stdout observed from an actual execution run. Check the report at `build/reports/tests/test/index.html`.

| Test Group | What It Proves |
| --- | --- |
| Spring AOP | `@PreAuthorize` applies to the Spring-managed service |
| Allow A/B with same ID 42 | Tenant isolation; same username does not mean same identity |
| Wrong tenant/authority | Denied **before** remote request/body executes |
| Same-name/different subject or issuer | Cannot borrow owner grants |
| Published without grant | Still denied |
| Grant/revoke | Next decision sees updated permissions when uncached |
| Unknown resource | Remote returns empty; policy denies |
| PDP error or timeout | Fails closed |
| Untrusted string principal | Identity cannot be forged from username alone |
| Cold Publisher | Neither remote nor body executes before subscription |
| Second subscription | Re-evaluates instead of memoizing stale decisions |
| WRITE | Modifies only matching tenant, owner, and `DRAFT` |
| READ only | Cannot invoke WRITE |
| PUBLISHED | Cannot be modified even by former owner |

### 7.3. Why Is This Project Truly Reactive?

`RemotePermissions.check` executes inside `Mono.defer` and then uses `Mono.delay(Duration.ofMillis(5))`; meaning the policy **does not immediately return a boolean on the caller thread**. `AsyncPolicy` composes the result via `flatMap`, followed by `timeout` and `defaultIfEmpty(false)`.

`contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))` binds the principal to the subscription; `@PreAuthorize` invokes the `authz` bean from the `ApplicationContext`. `Probe` sits inside the business service's `Mono.defer` so negative tests confirm zero business side effects. `Docs.write` uses a composite `tenant+ID` key and checks owner/state during mutation, never relying on `getName()` since both actors are named `alex`.

**Limitations:** this does not test `WebClient` TLS/network latency, database transactions, stale policy caches across cluster nodes, token refresh, or JWT revocation. For real `WRITE` operations, **commit-time authorization** may need to recheck versions/grants if security requirements forbid in-flight stale decisions.

## 8. Advanced Scenarios and Common Mistakes

### 8.1. `Flux` and RPC Volume

When a method returns `Flux<Document>`, `@PreAuthorize` can decide whether the **LIST operation** may be invoked; it does not replace object-level filtering. Never fire 50,000 concurrent PDP RPCs for 50,000 items. Use tenant/ACL predicates in the repository, batch policy lookups, or `flatMap(..., boundedConcurrency)` with backpressure.

### 8.2. Caching and Revocation

Permission caches must distinguish `(tenant, issuer, subject, action, type, resourceId, policyVersion)`. A cached ALLOW surviving past revocation opens a stale-permission window. TTL alone does not guarantee instant revocation; invalidate post-commit, increment revisions, and broadcast events across nodes. For sensitive `WRITE`/`DELETE`/`APPROVE` operations, consider rechecking at write time.

### 8.3. Failure Domains and Error Tagging

Do not lump every PDP failure together with `false` in metrics: record `decision=DENY`, `reason=not_granted`, and `reason=pdp_unavailable` in internal audits (never expose policy details to clients). On PDP timeouts, you may return 503 instead of 403 per API contract, but **never allow the operation to proceed**.

### 8.4. Cancellation, Retries, and Side Effects

When a client cancels a subscription, `Mono` propagates cancellation upstream. The remote HTTP call might still have run; decision endpoints must be idempotent. `retryWhen` must be bounded and never retry denials; never spawn a detached `.subscribe()` to "run a permission check in the background" while letting the body proceed.

### 8.5. AOP Proxies and Self-Invocation

`@PreAuthorize` applies to Spring-managed beans. Instantiating `new DocumentService(...)` bypasses the AOP proxy. Similarly, `this.write(...)` within the same target can bypass proxy advice; split service boundaries and test real call paths.

### 8.6. HTTP Security Does Not Replace Method Security

An API may block `GET /documents/42` in `SecurityWebFilterChain`, yet scheduled jobs or message consumers invoking the service directly bypass HTTP filters. Method security adds protection beneath the HTTP boundary. Conversely, method authorization does not control route-level CSRF, CORS, or HTTP authentication entry points.

## 9. Troubleshooting Table

| Symptom | Common Cause | Fix |
| --- | --- | --- |
| `Mono<Boolean>` not evaluated properly | Legacy reactive config / coercing SpEL operator | Verify `@EnableReactiveMethodSecurity` uses `AuthorizationManager`; bean returns `Mono<Boolean>` |
| Blocked-thread exception | `.block()` in WebFlux/event loop | Use reactive clients and return the publisher |
| Body runs before permission finishes | Manual `.subscribe()` followed by returning ALLOW | Use `flatMap` into a single decision publisher |
| `Mono<Mono<Boolean>>` | Using `map` for async callback | Switch to `flatMap` |
| Test sees no `Authentication` | Missing Reactor Context | Attach `contextWrite(withAuthentication(...))` |
| Same username shares permissions | Using `getName()` as unique identity | Key by `issuer`/`sub`/`tenant` |
| User A reads User B's doc with same ID | Remote lookup used ID only | Include tenant+type+ID and membership checks |
| Missing rule still allowed | Ambiguous `Mono.empty` semantics | Use `defaultIfEmpty(false)` in policy |
| Read succeeds during PDP outage | Fallback `true` or long-lived cached ALLOW | Fail closed, cache revisions/invalidation |
| All requests hang | Missing timeout | Timeouts + circuit breakers + metrics |
| WRITE runs without authority | Missing authority gate | Check authority before remote call; add negative tests |
| `@PreAuthorize` skipped | Bean not behind Spring proxy / self-invocation | Register Spring bean and test AOP proxy |
| Test passes even though body ran on deny | Asserting only the exception | Add probes and assert state stayed unchanged |
| Source runs blocking JDBC | `Mono.just(jdbc...)` still blocks | Use R2DBC or controlled offloading |
| In-flight write after revoke | TOCTOU | Transactions/conditional updates and grant/version rechecks |
| `Flux` sends too many PDP requests | Unbounded `flatMap` | Batching, concurrency caps, query filtering |

## 10. Practice Checklist

- [ ] Reactive method security is enabled; services return `Publisher`s and are called through Spring AOP proxies.
- [ ] `@authz` bean returns `Mono<Boolean>` composing async calls with `flatMap`, never `block()`.
- [ ] `Authentication` is read from Reactor Context; identity/tenant are verified and missing context fails closed.
- [ ] Action authorities are verified before remote I/O; READ/WRITE/EXPORT do not imply one another.
- [ ] PDP requests include tenant + stable subject + resource type/ID + action; never trust header-supplied tenant/subject.
- [ ] Missing rules, missing resources, timeouts, and errors ⇒ deny or fail-closed error contract.
- [ ] Timeouts, retries, concurrency limits, circuit breakers, and dedicated PDP-error metrics/audits are configured.
- [ ] Decision caches have TTLs, complete keys, and invalidation on permission changes.
- [ ] Business logic uses tenant-scoped repositories; writes enforce owner/state/version in transactions.
- [ ] Tests cover grant/revoke, same ID/different tenant, same name/different subject/issuer, and PDP errors/empty/hangs.
- [ ] No manual `.subscribe()` for decisions, and never assume one ALLOW lasts forever.
- [ ] For `Flux`/lists/exports, protect individual records and bound RPC volume.
- [ ] Run real Java tests before deployment and verify behavior on your specific Spring Security version.

## 11. Exercises

1. Replace `RemotePermissions` with `WebClient` calling a mock PDP; test 200 allow/deny, 404 empty, 503 error, and delays exceeding timeout.
2. Add `APPROVE` with separation of duties: makers cannot approve their own documents even with `DOC_APPROVE`.
3. Replace `Docs` with PostgreSQL R2DBC using a composite `(tenant, id)` key, and add optimistic versioning for `WRITE`.
4. Add a cache keyed by actor/tenant/action/resource/version; write a test verifying revocation after a cached ALLOW.
5. Use `StepVerifier` with two different principals on **the same publisher** and verify decisions do not share context.
6. Have the PDP return `Mono.never()`, configure an SLO-aligned timeout, and distinguish 403 vs. 503 in the API.
7. Implement `Flux<Document>` for LIST with tenant filtering and bounded concurrency for per-item checks.
8. Demonstrate how `this.write(...)` self-invocation bypasses Spring AOP, then fix the design using service boundaries.

## 12. Conclusion

A **Reactive Method Security** decision can call asynchronous permission services by having a bean in `@PreAuthorize` return `Mono<Boolean>`. Spring Security integrates the decision publisher with subscription, carries `Authentication` via Reactor Context, and denies execution before business logic runs when the policy forbids it.

```java
@PreAuthorize("@authz.canRead(#tenant, #id)")
public Mono<String> read(
        @P("tenant") String tenant,
        @P("id") long id) {
    return documentRepository.read(tenant, id);
}
```

Never turn `Mono` into `boolean` via `block()`, never split subscriptions with `.subscribe()`, and never treat empty/error/timeout as ALLOW. Bind **actor + tenant + action + resource + state** completely, paired with transactions and conditional updates where side effects happen. The test code in this lesson simulates an async PDP and shows expected results; run the Gradle tests in a real environment before deploying to production.

## Official References

- Spring Security 6.5 — Reactive Method Security and custom SpEL beans returning `Mono<Boolean>`: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
- Spring Security 6.5 — Reactive `PreAuthorizeReactiveAuthorizationManager`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/method/PreAuthorizeReactiveAuthorizationManager.html
- Project Reactor — Context: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Project Reactor — Operator choice: https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html
- Spring Security 6.5 — Reactive HTTP Authorization (distinct from method security): https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html
- OWASP API1:2023 — Broken Object Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
